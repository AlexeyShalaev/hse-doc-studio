"""Обзор файловой системы ХОСТА из контейнера — через сокет докера.

Мастер первоначальной настройки спрашивает папку на машине пользователя.
Заглянуть туда обычным `Path.iterdir()` нельзя: контейнер видит только свою
файловую систему. Зато демон резолвит `-v` против хоста, и одноразовый контейнер
с бинд-маунтом отвечает ровно на нужные вопросы: существует ли путь и что в нём
лежит. Так «выбрать папку» перестаёт быть печатанием вслепую.

Ключевое решение — монтировать не сам путь, а его КОРЕНЬ, и ходить внутри
контейнера. Иначе проверка портит диск: `docker run -v` несуществующий каталог
не отвергает, а СОЗДАЁТ, то есть опечатка выглядела бы как успешно найденная
пустая папка, оставляя за собой мусор. Корень же существует по определению, и
внутри него обычная проверка `-d` честно отвечает «нет такого».

Корень выбирается так, чтобы демон точно смог его отдать: на Windows это диск
(`C:/`), на POSIX — первый сегмент пути (`/Users`, `/home`). Целиком `/` брать
нельзя: Docker Desktop на macOS по умолчанию делится только `/Users`,
`/Volumes`, `/private` и `/tmp`.
"""

from __future__ import annotations

import re

import structlog

from hse_doc_studio.core.compile.docker_diagnosis import (
    DockerUnavailableReason,
    classify_docker_error,
    classify_mount_error,
)
from hse_doc_studio.core.setup import MountProbeResult, MountProbeStatus, ProbeEntry
from hse_doc_studio.infra.docker.cli import run_docker
from hse_doc_studio.infra.runtime.environment import self_container_ref

logger = structlog.get_logger()

_PROBE_TIMEOUT_S = 40.0
_INSPECT_TIMEOUT_S = 5.0
_HEALTH_TIMEOUT_S = 5.0
_MAX_ENTRIES = 400

# Файлы, по которым узнаётся каталог данных ПРЕЖНЕЙ установки: реестр
# проектов и настройки кладутся туда первыми и живут всегда.
_INSTALL_MARKERS: frozenset[str] = frozenset({"projects.json", "config.json"})
_FALLBACK_IMAGE = "alpine:latest"

_DRIVE_RE = re.compile(r"^([A-Za-z]:)(?:/(.*))?$")

_MOUNT_POINT = "/probe"
_MISSING = "__HSE_MISSING__"
_ENTRIES_END = "__HSE_ENTRIES_END__"
_WRITABLE = "__HSE_WRITABLE__"
_DISK = "__HSE_DISK__"
_WRITE_MARKER = ".hse-studio-write-probe"

# Остаток пути приезжает переменной окружения, а не подстановкой в скрипт: в
# именах папок бывают пробелы, кавычки и кириллица, и склеивать их со строкой
# команды — верный способ однажды выполнить не то.
#
# Тип каждого элемента определяется `-d`, а не суффиксом от `ls -p`: на Windows
# домашние каталоги часто оказываются junction-точками, которые `-p` каталогами
# не считает, а `-d` — считает, пройдя по ссылке.
_PROBE_SCRIPT = f"""
set -u
TARGET="{_MOUNT_POINT}${{HSE_REL:+/$HSE_REL}}"
if [ ! -d "$TARGET" ]; then
  echo {_MISSING}
  exit 0
fi
ls -A "$TARGET" 2>/dev/null | head -n {_MAX_ENTRIES} | while IFS= read -r name; do
  if [ -d "$TARGET/$name" ]; then printf 'd\\t%s\\n' "$name"; else printf 'f\\t%s\\n' "$name"; fi
done
echo {_ENTRIES_END}
DF="$(df -Pk "$TARGET" 2>/dev/null | tail -1)"
if [ -n "$DF" ]; then
  # `df -P` гарантирует одну строку на файловую систему, поэтому позиционный
  # разбор здесь надёжен: 2-е поле — всего килобайт, 4-е — доступно.
  set -- $DF
  printf '{_DISK}\\t%s\\t%s\\n' "$2" "$4"
fi
touch "$TARGET/{_WRITE_MARKER}" 2>/dev/null && rm -f "$TARGET/{_WRITE_MARKER}" && echo {_WRITABLE}
# Явный ноль в конце обязателен. Иначе кодом возврата всего скрипта становится
# результат проверки записи, и НЕзаписываемый каталог — например `C:/Users`,
# через который проходит каждый пользователь Windows, — выглядел бы как
# несостоявшееся монтирование. Права на запись здесь справка, а не приговор:
# ходить по такой папке можно, просто хранить в ней работы нельзя.
exit 0
"""


def split_anchor(host_path: str) -> tuple[str, str]:
    """Путь → (корень, который монтируем, остаток внутри него).

    Корень обязан существовать заведомо, иначе монтирование само его создаст.
    Диск на Windows и первый сегмент на POSIX этому условию удовлетворяют:
    первый пользователь всё равно приходит из `/Users` или `/home`, а глубже
    мы уже спускаемся по подтверждённым каталогам.
    """
    normalised = host_path.replace("\\", "/").strip()
    drive = _DRIVE_RE.match(normalised)
    if drive is not None:
        return f"{drive.group(1)}/", (drive.group(2) or "").strip("/")
    if not normalised.startswith("/"):
        return normalised, ""
    segments = [s for s in normalised.split("/") if s]
    if not segments:
        return "/", ""
    return f"/{segments[0]}", "/".join(segments[1:])


class DockerHealthProbe:
    """Отвечает ли демон, и если нет — по какой из известных причин."""

    async def check(self) -> tuple[bool, DockerUnavailableReason | None]:
        rc, _out, err = await run_docker(["version", "--format", "{{.Server.Version}}"], timeout=_HEALTH_TIMEOUT_S)
        if rc == 0:
            return True, None
        if rc is None:
            reason = DockerUnavailableReason.TIMEOUT if "timed out" in err else DockerUnavailableReason.CLI_MISSING
            return False, reason
        return False, classify_docker_error(err)


class MountProbe:
    """Одноразовый контейнер с бинд-маунтом корня проверяемого пути."""

    def __init__(self, *, fallback_image: str = _FALLBACK_IMAGE) -> None:
        self._fallback_image = fallback_image
        self._image: str | None = None

    async def probe(self, host_path: str) -> MountProbeResult:
        anchor, relative = split_anchor(host_path)
        image = await self._probe_image()
        rc, out, err = await run_docker(
            [
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                # От root: контейнер сборки тоже работает от него, и вопрос у нас
                # ровно про его возможности, а не про непривилегированного `app`
                # из нашего образа.
                "--user",
                "0:0",
                "-e",
                f"HSE_REL={relative}",
                "-v",
                f"{anchor}:{_MOUNT_POINT}",
                image,
                "-c",
                _PROBE_SCRIPT,
            ],
            timeout=_PROBE_TIMEOUT_S,
        )
        if rc is None:
            unavailable = "not found" in err or "timed out" not in err
            status = MountProbeStatus.docker_unavailable if unavailable else MountProbeStatus.timeout
            return MountProbeResult(status=status, detail=err.strip() or None)
        if rc != 0:
            reason = classify_mount_error(err)
            logger.info("mount probe rejected", host_path=host_path, anchor=anchor, reason=str(reason))
            return MountProbeResult(
                status=MountProbeStatus.mount_failed,
                reason=reason,
                detail=err.strip() or None,
            )
        return _parse_probe_output(out)

    async def _probe_image(self) -> str:
        """Свой образ, если мы в контейнере; иначе — маленький публичный.

        Свой заведомо есть локально, поэтому обзор не ходит в сеть и работает в
        закрытом контуре. Нативный запуск такой гарантии не даёт: там остаётся
        общедоступный образ, который докер при необходимости подтянет сам.
        """
        if self._image is not None:
            return self._image
        self_ref = self_container_ref()
        if self_ref is not None:
            rc, out, _err = await run_docker(
                ["inspect", "-f", "{{.Config.Image}}", self_ref],
                timeout=_INSPECT_TIMEOUT_S,
            )
            own = out.strip()
            if rc == 0 and own:
                self._image = own
                return own
        self._image = self._fallback_image
        return self._image


def _parse_probe_output(out: str) -> MountProbeResult:
    lines = out.splitlines()
    if _MISSING in lines:
        return MountProbeResult(status=MountProbeStatus.ok, exists=False)
    try:
        end = lines.index(_ENTRIES_END)
    except ValueError:
        # Скрипт не доработал до маркера. Монтирование состоялось (docker вернул
        # ноль), но содержимому доверять нельзя — честнее отдать пустой список,
        # чем неполный, выдав его за полный.
        return MountProbeResult(status=MountProbeStatus.ok, exists=True, is_empty=True)
    entries = tuple(_entry(line) for line in lines[:end] if "\t" in line)
    tail = lines[end + 1 :]
    total_kb, free_kb = _disk(tail)
    return MountProbeResult(
        status=MountProbeStatus.ok,
        exists=True,
        entries=entries,
        is_empty=not entries,
        writable=_WRITABLE in tail,
        looks_like_install=any(not e.is_dir and e.name in _INSTALL_MARKERS for e in entries),
        total_bytes=total_kb * 1024 if total_kb is not None else None,
        free_bytes=free_kb * 1024 if free_kb is not None else None,
    )


def _entry(line: str) -> ProbeEntry:
    kind, _, name = line.partition("\t")
    return ProbeEntry(name=name, is_dir=kind == "d")


def _disk(lines: list[str]) -> tuple[int | None, int | None]:
    """Всего и свободно килобайт из строки `df`; None — строки нет или она битая."""
    fields = 3
    for line in lines:
        if not line.startswith(_DISK):
            continue
        parts = line.split("\t")
        if len(parts) != fields or not parts[1].isdigit() or not parts[2].isdigit():
            return None, None
        return int(parts[1]), int(parts[2])
    return None, None
