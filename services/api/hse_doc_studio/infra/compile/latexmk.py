"""Общее у исполнителей TeX (docker и kubernetes): команда latexmk, сентинелы потока и разбор итогов сборки."""

from __future__ import annotations

import re
import shlex
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SENTINEL_DONE = "__DONE__"
SENTINEL_FAILED = "__FAILED__"
# Carries the page count of a successful build back to the runner so it can be
# persisted on the CompileRecord (and shown in the UI). Not a log line.
SENTINEL_PAGES = "__PAGES__:"
# Carries the prose word + character totals back to the runner as
# "__WORDS__:<words>:<chars>". Computed by texcount, not a log line.
SENTINEL_WORDS = "__WORDS__:"

# xelatex/latexmk print "Output written on <file>.xdv (N pages, ...)" in the
# per-document .log on a successful run. TeX wraps log lines at max_print_line
# (79, env override ignored since TL2023) — long .build/<doc_id>/ paths push
# "(N pages" across the wrap, even mid-number. `\s+` tolerates a wrap between
# the count and "page"; extract_log_page_count retries on an unwrapped log
# for the mid-number case.
_LOG_PAGE_COUNT_RE = re.compile(r"Output written on [^()]+\((\d+)\s+page")

# texcount -1 prints one line "text+headers+captions (h/f/i/d) Total"; we sum
# the first three integers (the parts that render as prose, headings included).
_TEXCOUNT_TOTAL_RE = re.compile(r"^\s*(\d+)\+(\d+)\+(\d+)\b")

# Map our EngineType strings onto latexmk's mode-selector flags. Latexmk
# decides how many engine + biber + makeindex passes to run; we just tell it
# which engine to use as the PDF-producing rule.
ENGINE_FLAG = {
    "xelatex": "-xelatex",
    "lualatex": "-lualatex",
    "pdflatex": "-pdf",
}

NONROOT_TEX_ENV = (
    ("HOME", "/tmp"),  # noqa: S108
    ("TEXMFVAR", "/tmp/texmf-var"),  # noqa: S108
    ("TEXMFCONFIG", "/tmp/texmf-config"),  # noqa: S108
)

# Поиск входов от корня проекта и одна строка «Output written on … (N pages» в логе (для старых образов).
TEX_SEARCH_ENV = (
    ("TEXINPUTS", "/work:"),
    ("BIBINPUTS", "/work:"),
    ("BSTINPUTS", "/work:"),
    ("max_print_line", "10000"),
)

# Воспроизводимая сборка: те же исходники в том же образе дают байт в байт тот же PDF у любого исполнителя, поэтому
# пересборка без правок не сбрасывает фиксацию подписей и маршрут подписания. Иначе каждая сборка даёт свой PDF:
# дата создания в свойствах и `/ID` в трейлере. SOURCE_DATE_EPOCH задаёт эту дату, а `/ID` движки считают от неё и
# путей сборки (xdvipdfmx: дата, производитель, имена .xdv и .pdf; pdfTeX и LuaTeX: дата, имя и рабочий каталог),
# так что `\pdftrailerid{}` не нужен. Дата постоянная, а не от снимка проекта: снимок «Сборка» после каждой сборки с
# правками сдвигал бы её, и следующая пересборка без правок дала бы другой PDF; облако и Студия с разной историей
# тоже собрали бы разные. FORCE_SOURCE_DATE=0 оставляет `\today`, `\the\year` и `\time` настоящими.
SOURCE_DATE_EPOCH = 315532800  # 1980-01-01T00:00:00Z
REPRODUCIBLE_TEX_ENV = (
    ("SOURCE_DATE_EPOCH", str(SOURCE_DATE_EPOCH)),
    ("FORCE_SOURCE_DATE", "0"),
)
# Комментарий в заголовке DVI/XDV: TeX пишет туда настоящие дату и минуту сборки («XeTeX output 2026.11.13:2231»,
# FORCE_SOURCE_DATE=0 их не трогает), а xdvipdfmx кладёт его в `/Creator` PDF, если документ не задал свой (hyperref
# задаёт). Без постоянного комментария документ без hyperref, собранный в другую минуту, давал другой PDF. Для
# pdfTeX и LuaTeX в режиме PDF опция ничего не меняет.
OUTPUT_COMMENT = "hse-doc-studio"
REPRODUCIBLE_LATEXMK_OPTIONS = (f"-latexoption=-output-comment={OUTPUT_COMMENT}",)

# Под не-root формат движка собирается заранее вне `-output-directory`, см. DockerCompileExecutor._tex_launcher.
NONROOT_FORMAT_PREPARE = 'cd /tmp && fmtutil-user --byfmt "$0" >&2; cd "$OLDPWD" && exec "$@"'


@dataclass(frozen=True)
class TexSource:
    """Где лежит документ: рабочий каталог в контейнере, имя файла и каталог сборки относительно корня проекта."""

    workdir: str
    basename: str
    stem: str
    parent: str
    build_subdir: str

    @property
    def build_rel(self) -> str:
        """`.build/<doc_id>` от корня проекта (а не от каталога документа)."""
        return self.build_subdir if self.parent in ("", ".") else f"{self.parent}/{self.build_subdir}"


def tex_source(source_file: str, doc_id: str) -> TexSource:
    """Engines resolve relative `\\input{../foo}` against cwd, so the build runs in the .tex's directory."""
    src_posix = PurePosixPath(source_file.replace("\\", "/"))
    parent = src_posix.parent.as_posix() if src_posix.parent.parts else ""
    basename = src_posix.name
    workdir = "/work" if parent in ("", ".") else f"/work/{parent}"
    return TexSource(
        workdir=workdir,
        basename=basename,
        stem=PurePosixPath(basename).stem,
        parent=parent,
        build_subdir=f".build/{doc_id}",
    )


def latexmk_argv(engine_flag: str, max_iterations: int, src: TexSource) -> list[str]:
    return [
        "latexmk",
        engine_flag,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-synctex=1",
        f"-output-directory={src.build_subdir}",
        *REPRODUCIBLE_LATEXMK_OPTIONS,
        "-e",
        f"$max_repeat={max_iterations};",
        src.basename,
    ]


def texcount_command(basename: str, *, chars: bool) -> str:
    """texcount has no `--` end-of-options marker; shlex.quote guards spaces/specials for the shell."""
    flag = " -char" if chars else ""
    return f"texcount -inc -1{flag} {shlex.quote(basename)} 2>/dev/null"


def reset_latexmk_state(build_dir: Path, stem: str) -> None:
    """Delete latexmk's per-document file database after a failed run.

    latexmk records each rule's success/failure in `<stem>.fdb_latexmk`. Left
    behind after a failure, it makes the next compile of unchanged source exit
    12 ("gave an error in previous invocation") without re-running the engine.
    Removing it forces a clean re-run; the `.log` is intentionally preserved.
    """
    with suppress(OSError):
        (build_dir / f"{stem}.fdb_latexmk").unlink(missing_ok=True)


def sum_texcount_total(block: str) -> int | None:
    """Sum text+headers+captions from a texcount `-1` total line, or None."""
    for line in block.splitlines():
        m = _TEXCOUNT_TOTAL_RE.match(line)
        if m is not None:
            return int(m.group(1)) + int(m.group(2)) + int(m.group(3))
    return None


def extract_log_page_count(log_path: Path) -> int | None:
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _LOG_PAGE_COUNT_RE.search(text)
    if m is None:
        # TeX hard-wraps log lines at max_print_line (79, not overridable via
        # the environment since TL2023), and for long .build/<doc_id>/ paths
        # the wrap can land anywhere inside "(N pages" — even mid-number
        # ("(2\n6 pages"). Retry against the log with newlines removed: the
        # "Output written on" phrase is unique, so unwrapping is safe.
        m = _LOG_PAGE_COUNT_RE.search(text.replace("\n", ""))
    return int(m.group(1)) if m is not None else None
