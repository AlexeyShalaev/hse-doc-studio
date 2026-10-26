"""Поддельный `docker` для сквозных тестов сборки.

Настоящие `DockerCompileExecutor` и `CompileRunner` запускают подпроцесс, читают
его stdout и убивают его сигналами. Подмена самого исполнителя скрыла бы именно
эти места, поэтому подменяется только бинарник: в `docker_binary()` попадает
исполняемый sh-скрипт, который ведёт себя как `docker run ... latexmk` и как
`docker run ... texcount`.

Скрипт сам разбирает аргументы, которые строит исполнитель (`-v <host>:/work:z`,
`-w <workdir>`, `-output-directory=...`, имя исходника последним), и кладёт
артефакты туда, куда их положил бы latexmk в контейнере: `<stem>.pdf` и
`<stem>.log` в `.build/<doc_id>/`. Поведение задаётся при установке: сколько
строк напечатать, сколько «собирать», реагировать ли на SIGTERM, каким кодом
выйти. Все вызовы и полученные сигналы записываются в файлы, их читает тест.
"""

from __future__ import annotations

import shlex
import stat
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from hse_doc_studio.infra.docker import cli as docker_cli

_TICK_S = 0.1

_SCRIPT = """#!/bin/sh
CALLS={calls}
MARKERS={markers}
printf '%s\\n' "$*" >> "$CALLS"

for a in "$@"; do last="$a"; done

case "$last" in
  *texcount*)
    {texcount}
    exit 0
    ;;
esac

case " $* " in
  *" latexmk "*) ;;
  *) exit 0 ;;
esac

host=""; workdir=""; outdir=""; prev=""
for a in "$@"; do
  case "$prev" in
    -v) case "$a" in *:/work:z) host="${{a%:/work:z}}" ;; esac ;;
    -w) workdir="$a" ;;
  esac
  case "$a" in -output-directory=*) outdir="${{a#-output-directory=}}" ;; esac
  prev="$a"
done
build="$host${{workdir#/work}}/$outdir"
stem="${{last%.*}}"

{term_trap}
echo started >> "$MARKERS"

{output}

ticks={ticks}
while [ "$ticks" -gt 0 ]; do
  sleep {tick} &
  child=$!
  wait "$child"
  ticks=$((ticks - 1))
done

mkdir -p "$build"
if [ {exit_code} -ne 0 ]; then
  : > "$build/$stem.fdb_latexmk"
  printf '! LaTeX Error: fake failure.\\n' > "$build/$stem.log"
  exit {exit_code}
fi
printf 'This is XeTeX, fake.\\nOutput written on %s.xdv ({pages} pages, 1234 bytes).\\n' "$stem" > "$build/$stem.log"
printf '%%PDF-1.4 fake build\\n' > "$build/$stem.pdf"
exit 0
"""


@dataclass(frozen=True)
class FakeDocker:
    script: Path
    calls_file: Path
    markers_file: Path

    def calls(self) -> list[str]:
        """Все вызовы docker: по строке на вызов (аргументы через пробел)."""
        return _lines(self.calls_file)

    def build_calls(self) -> list[str]:
        """Только запуски latexmk."""
        return [c for c in self.calls() if " latexmk " in f" {c} "]

    def markers(self) -> list[str]:
        """События внутри «контейнера»: `started`, `term` (SIGTERM принят), `term-ignored`."""
        return _lines(self.markers_file)


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]


def install_fake_docker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    output_lines: Sequence[str] = ("fake latexmk: line 1", "fake latexmk: line 2"),
    duration_s: float = 0.0,
    ignore_term: bool = False,
    exit_code: int = 0,
    pages: int = 7,
    texcount: tuple[str, str] | None = ("12+3+4 (1/0/0/0) Total", "100+20+5 (1/0/0/0) Total"),
) -> FakeDocker:
    """Направить `docker_binary()` на скрипт-пустышку.

    `duration_s` — сколько «собираться» после печати строк; для сценариев отмены и
    таймаута тишины ставится заведомо больше, чем живёт тест. `ignore_term` —
    скрипт игнорирует SIGTERM, и остановить его можно только SIGKILL.
    `texcount=None` — второй вызов (подсчёт слов) молчит.

    Подмена стоит на самом объекте, который читает `docker_binary()`, поэтому
    достаёт до любого вызывающего, как бы он ни импортировал функцию; после теста
    monkeypatch возвращает всё как было.
    """
    work_dir = tmp_path / "fake-docker"
    work_dir.mkdir(parents=True, exist_ok=True)
    script = work_dir / "docker"
    calls_file = work_dir / "calls.log"
    markers_file = work_dir / "markers.log"

    if ignore_term:
        term_trap = "trap 'echo term-ignored >> \"$MARKERS\"' TERM"
    else:
        term_trap = 'trap \'echo term >> "$MARKERS"; kill "$child" 2>/dev/null; exit 143\' TERM'

    if texcount is None:
        texcount_block = ":"
    else:
        words, chars = texcount
        texcount_block = f"echo {shlex.quote(words)}; echo ___HSE_TEXCOUNT_SEP___; echo {shlex.quote(chars)}"

    output = "\n".join(f"echo {shlex.quote(line)}" for line in output_lines) or ":"
    script.write_text(
        _SCRIPT.format(
            calls=shlex.quote(str(calls_file)),
            markers=shlex.quote(str(markers_file)),
            texcount=texcount_block,
            term_trap=term_trap,
            output=output,
            ticks=round(duration_s / _TICK_S),
            tick=_TICK_S,
            exit_code=exit_code,
            pages=pages,
        ),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Первый запуск свежего скрипта на macOS занимает до пары секунд (проверка файла
    # системой). Прогреваем его здесь, иначе таймер тишины в исполнителе успевает
    # сработать раньше, чем шелл стартует. Безобидный вызов выходит на ветке `exit 0`,
    # его следы в журналах стираем, чтобы счётчики вызовов остались чистыми.
    subprocess.run([str(script), "--warmup"], check=True, capture_output=True)
    calls_file.unlink(missing_ok=True)
    markers_file.unlink(missing_ok=True)

    monkeypatch.setattr(docker_cli._docker_binary, "get", lambda: str(script))
    return FakeDocker(script=script, calls_file=calls_file, markers_file=markers_file)
