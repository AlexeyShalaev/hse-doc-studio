"""Готова ли установка к работе — и если нет, что именно не так.

Продукт запускается одной командой докера, и в этой команде легко ошибиться так,
что приложение откроется, а работать не будет:

* забыт бинд каталога — проекты окажутся ВНУТРИ контейнера и исчезнут при первом
  же обновлении версии;
* `DATA_DIR` оставлен относительным (`./data`, ровно как в примере `.env`) —
  демон примет такой путь за имя тома, соответствие «контейнер ↔ хост» не
  зарегистрируется, и ни один документ не соберётся;
* сокет докера не проброшен — собирать нечем вовсе.

Ни один из трёх случаев раньше не имел имени: приложение писало предупреждение в
лог, которого пользователь не читает, и молча вело себя как сломанное. Поэтому
«настроено ли» здесь — явное состояние приложения: считается на старте,
показывается в интерфейсе и чинится мастером первоначальной настройки.

Тексты причин живут в словарях интерфейса, а не здесь: домен отдаёт
машиночитаемый код и подстановки к нему.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.compile.docker_diagnosis import DockerUnavailableReason, MountFailureReason
from hse_doc_studio.core.paths import Mount


class SetupCheckId(StrEnum):
    """Что именно проверяем."""

    docker = "docker"
    """Отвечает ли демон докера: без него не собирается ни один документ."""

    project_storage = "project_storage"
    """Лежат ли файлы пользователя на его машине, а не внутри контейнера."""


class SetupSeverity(StrEnum):
    ok = "ok"
    warning = "warning"
    """Работать можно, но что-то из возможностей продукта отключено."""

    blocker = "blocker"
    """Продукт в этом состоянии не выполняет свою работу — нужен мастер настройки."""


@dataclass(frozen=True)
class SetupCheck:
    id: SetupCheckId
    severity: SetupSeverity
    code: str
    """Машиночитаемая причина: интерфейс подбирает по ней текст и подсказку."""

    context: Mapping[str, str] = field(default_factory=dict)
    """Подстановки к тексту — путь, gid сокета и подобное."""

    @property
    def is_blocker(self) -> bool:
        return self.severity is SetupSeverity.blocker


@dataclass(frozen=True)
class SetupReport:
    checks: tuple[SetupCheck, ...]
    compose_project: str | None = None
    """Имя compose-проекта, если контейнер поднят им; None — обычный `docker run`.

    Мастер применяет выбор пересозданием контейнера, и для compose-установки
    этого мало: файл и `.env` остались прежними, а первый же
    `docker compose up -d` вернёт старую конфигурацию. Такому пользователю
    показываем не кнопку, а строку, которую надо поправить.
    """

    @property
    def blockers(self) -> tuple[SetupCheck, ...]:
        return tuple(c for c in self.checks if c.is_blocker)

    @property
    def is_ready(self) -> bool:
        """Можно ли работать. False — интерфейс обязан показать мастер настройки."""
        return not self.blockers

    @property
    def can_self_apply(self) -> bool:
        """Может ли мастер починить установку сам, не отсылая пользователя в файлы."""
        return self.compose_project is None


def assess_docker(*, alive: bool, reason_code: str | None = None, socket_gid: int | None = None) -> SetupCheck:
    """Доступность демона. `reason_code` — уточнение из `classify_docker_error`.

    Заметьте: не blocker. Мёртвый демон — не ошибка УСТАНОВКИ, а состояние
    машины: докер можно запустить и через минуту, ничего не пересоздавая. И
    приложение при нём остаётся наполовину живым — тексты правятся, готовые PDF
    читаются, — так что запирать за мастером весь интерфейс было бы вредительством.
    Про недоступный докер рассказывает отдельный баннер, а мастер учитывает эту
    проверку иначе: без сокета он не сможет пересоздать себя и вместо кнопки
    показывает команду для терминала.
    """
    if alive:
        return SetupCheck(id=SetupCheckId.docker, severity=SetupSeverity.ok, code="ok")
    # gid владельца сокета читается даже без права им пользоваться — и это
    # единственная причина отказа, которую пользователь чинит ДЕТЕРМИНИРОВАННО:
    # добавить контейнер в эту группу. Даём точное число, а не совет посчитать
    # его самому.
    context = {"socket_gid": str(socket_gid)} if socket_gid is not None else {}
    return SetupCheck(
        id=SetupCheckId.docker,
        severity=SetupSeverity.warning,
        code=reason_code or "daemon_unreachable",
        context=context,
    )


def assess_project_storage(
    *,
    in_container: bool,
    mounts: Sequence[Mount],
    host_data_dir: str | None,
) -> SetupCheck:
    """Видит ли пользователь свои файлы у себя на машине.

    Нативный запуск проверять нечего: файловая система одна. В контейнере же
    рабочим является ровно одно состояние — есть хотя бы одна пара «путь внутри ↔
    путь на хосте». Разбираем два способа её не получить по отдельности, потому
    что чинятся они по-разному: в первом случае бинд не задан вовсе, во втором
    задан, но относительным путём, и человек уверен, что всё настроил.
    """
    if not in_container:
        return SetupCheck(id=SetupCheckId.project_storage, severity=SetupSeverity.ok, code="native")
    if mounts:
        return SetupCheck(
            id=SetupCheckId.project_storage,
            severity=SetupSeverity.ok,
            code="ok",
            context={"host_path": mounts[0].host},
        )
    if host_data_dir:
        # Задан, но непригоден — единственный случай, когда пользователь считает,
        # что настроил всё правильно. Показываем ему ровно то, что он написал.
        return SetupCheck(
            id=SetupCheckId.project_storage,
            severity=SetupSeverity.blocker,
            code="relative_host_path",
            context={"host_path": host_data_dir},
        )
    return SetupCheck(id=SetupCheckId.project_storage, severity=SetupSeverity.blocker, code="no_host_path")


def build_report(checks: Sequence[SetupCheck], *, compose_project: str | None = None) -> SetupReport:
    return SetupReport(checks=tuple(checks), compose_project=compose_project)


# ── Проверка папки на машине пользователя ───────────────────────────────────


class MountProbeStatus(StrEnum):
    ok = "ok"
    mount_failed = "mount_failed"
    docker_unavailable = "docker_unavailable"
    timeout = "timeout"


@dataclass(frozen=True)
class ProbeEntry:
    """Элемент каталога хоста, увиденный через одноразовый контейнер."""

    name: str
    is_dir: bool


@dataclass(frozen=True)
class MountProbeResult:
    """Чем закончилась попытка заглянуть в конкретную папку хоста."""

    status: MountProbeStatus
    exists: bool = False
    """Есть ли такая папка. Отличать от пустой обязательно: опечатка в пути даёт
    именно пустую папку, если проверять её монтированием напрямую."""

    entries: tuple[ProbeEntry, ...] = ()
    """Содержимое. По нему человек узнаёт своё место на диске и ходит вглубь."""

    is_empty: bool = False
    writable: bool = False
    looks_like_install: bool = False
    """Похожа ли папка на каталог данных ПРЕЖНЕЙ установки.

    Сценарий переустановки: человек указывает старую папку и не знает, безопасно
    ли это — сотрёт мастер его работы или подхватит. Молчание здесь читается как
    угроза, поэтому узнавание своих же файлов обязано быть явным.
    """

    free_bytes: int | None = None
    """Сколько места осталось на диске с этой папкой.

    Цифра не косметическая: на первой же сборке докер скачивает образ TeX Live —
    несколько гигабайт, — и узнать об их отсутствии посреди сборки гораздо хуже,
    чем при выборе папки.
    """

    total_bytes: int | None = None
    reason: MountFailureReason | None = None
    detail: str | None = None
    """Сырой текст докера — на случай причины, которой мы не знаем."""

    @property
    def is_ok(self) -> bool:
        return self.status is MountProbeStatus.ok

    @property
    def directories(self) -> tuple[ProbeEntry, ...]:
        return tuple(e for e in self.entries if e.is_dir)


class IMountProbe(Protocol):
    """Может ли демон отдать нам эту папку хоста и что в ней лежит."""

    async def probe(self, host_path: str) -> MountProbeResult: ...


class IDockerHealthProbe(Protocol):
    """Отвечает ли демон, и если нет — почему."""

    async def check(self) -> tuple[bool, DockerUnavailableReason | None]: ...


class ISelfContainerInfo(Protocol):
    """Кто управляет нашим контейнером."""

    async def compose_project(self) -> str | None: ...


# ── Что за машина под нами и чем именно нас запустили ───────────────────────
#
# Всё это пользователю неоткуда узнать: интерфейс живёт в контейнере, «О
# программе» до окончания настройки недоступна, а команду запуска он мог
# скопировать не читая. При этом цифры не справочные — от них зависит, сколько
# сборок пойдёт параллельно и хватит ли места образу TeX Live.


@dataclass(frozen=True)
class DockerEngineInfo:
    """Ресурсы, которые достанутся КОНТЕЙНЕРАМ, а не всей машине.

    Разница существенна на Docker Desktop: там между хостом и демоном стоит
    виртуальная машина со своей квотой, и человек с 64 ГБ памяти вполне может
    отдать сборкам четыре.
    """

    server_version: str
    os_type: str
    operating_system: str
    architecture: str
    cpus: int
    memory_bytes: int


@dataclass(frozen=True)
class ContainerMount:
    source: str
    destination: str
    read_only: bool


@dataclass(frozen=True)
class ContainerRuntimeInfo:
    """Параметры, с которыми запущены МЫ САМИ — как их видит докер."""

    image: str
    published_ports: tuple[str, ...]
    mounts: tuple[ContainerMount, ...]
    socket_mounted: bool
    group_add: tuple[str, ...]
    restart_policy: str
    network_mode: str


@dataclass(frozen=True)
class HostFontsInfo:
    """Откуда приложение возьмёт шрифты пользователя.

    Показывается на экране настройки, потому что автоопределение может
    промахнуться: каталог перебирается по стандартным местам, а держать шрифты
    можно где угодно. Увидев не тот путь, человек поправит его до того, как
    документ соберётся не тем начертанием.
    """

    directory: str | None
    count: int


@dataclass(frozen=True)
class SetupEnvironment:
    engine: DockerEngineInfo | None
    container: ContainerRuntimeInfo | None
    fonts: HostFontsInfo | None = None


class IEnvironmentProbe(Protocol):
    """Сведения о движке докера и о собственном контейнере."""

    async def describe(self) -> SetupEnvironment: ...


class ISetupApplier(Protocol):
    """Применить выбранную папку: пересоздать приложение с нужным бинд-маунтом.

    True — пересоздание ЗАПУЩЕНО, а не завершено: этот процесс переживает
    собственную смерть, и дождаться результата ему неоткуда.
    """

    async def apply(
        self,
        *,
        data_host_path: str,
        fonts_host_path: str | None = None,
        prefetch_tex_image: bool = True,
    ) -> bool: ...
