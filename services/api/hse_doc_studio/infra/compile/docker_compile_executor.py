from __future__ import annotations

import asyncio
import re
import shlex
import shutil
import uuid
from asyncio import subprocess as asubprocess
from collections.abc import AsyncGenerator, Callable
from contextlib import suppress
from pathlib import Path, PurePosixPath

import structlog

from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.docker.cli import docker_binary

logger = structlog.get_logger()

_SENTINEL_DONE = "__DONE__"
_SENTINEL_FAILED = "__FAILED__"
# Retries for moving the built PDF into place: on Windows the target can be
# transiently locked by antivirus/indexing/an open viewer (WinError 32).
_PDF_MOVE_ATTEMPTS = 5
_PDF_MOVE_RETRY_DELAY_S = 0.6
# Carries the page count of a successful build back to the runner so it can be
# persisted on the CompileRecord (and shown in the UI). Not a log line.
_SENTINEL_PAGES = "__PAGES__:"
# Carries the prose word + character totals back to the runner as
# "__WORDS__:<words>:<chars>". Computed by texcount, not a log line.
_SENTINEL_WORDS = "__WORDS__:"

# xelatex/latexmk print "Output written on <file>.xdv (N pages, ...)" in the
# per-document .log on a successful run. TeX wraps log lines at max_print_line
# (79, env override ignored since TL2023) — long .build/<doc_id>/ paths push
# "(N pages" across the wrap, even mid-number. `\s+` tolerates a wrap between
# the count and "page"; _extract_log_page_count retries on an unwrapped log
# for the mid-number case.
_LOG_PAGE_COUNT_RE = re.compile(r"Output written on [^()]+\((\d+)\s+page")

# texcount -1 prints one line "text+headers+captions (h/f/i/d) Total"; we sum
# the first three integers (the parts that render as prose, headings included).
_TEXCOUNT_TOTAL_RE = re.compile(r"^\s*(\d+)\+(\d+)\+(\d+)\b")

DEFAULT_IDLE_TIMEOUT_S = 120.0
DEFAULT_IMAGE = "texlive/texlive:TL2024-historic"
DEFAULT_CACHE_VOLUME = "hse-tex-cache"
DEFAULT_CACHE_TARGET = "/root"

_PROCESS_TERMINATE_TIMEOUT_S = 5.0

# Map our EngineType strings onto latexmk's mode-selector flags. Latexmk
# decides how many engine + biber + makeindex passes to run; we just tell it
# which engine to use as the PDF-producing rule.
_ENGINE_FLAG = {
    "xelatex": "-xelatex",
    "lualatex": "-lualatex",
    "pdflatex": "-pdf",
}


ProcessCallback = Callable[[asubprocess.Process], None]


class DockerCompileExecutor:
    """Runs latexmk in a single ephemeral TeX Live container.

    One `docker run` per compile, regardless of how many engine passes
    latexmk decides are needed for convergence. A named Docker volume
    mounted at /root persists font and format caches across compiles,
    turning the second and subsequent compiles from cold-cache ~10s
    starts into hot-cache sub-second starts.

    Per-document output (.aux/.log/.pdf/.synctex.gz/...) lands in a
    `.build/<doc_id>/` directory next to the source. On success the
    PDF is moved up next to the source so the existing preview URL
    keeps working without changes; on failure artifacts stay in
    `.build/` for inspection.

    When the backend is itself containerized, the bind-mount source
    for /work must be a HOST path that the daemon understands, not
    the in-container path the backend sees — `HostPathResolver` does
    that prefix swap.
    """

    def __init__(
        self,
        host_path_resolver: HostPathResolver,
        image: str = DEFAULT_IMAGE,
        cache_volume_name: str = DEFAULT_CACHE_VOLUME,
        cache_volume_target: str = DEFAULT_CACHE_TARGET,
        idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S,
        fonts_dir: Path | None = None,
        fonts_host_dir: str | None = None,
        fonts_mount_target: str = "/usr/local/share/fonts/hse",
    ) -> None:
        self._resolver = host_path_resolver
        self._image = image
        self._cache_volume_name = cache_volume_name
        self._cache_volume_target = cache_volume_target
        self._idle_timeout_s = idle_timeout_s
        # Managed local fonts: when the folder holds any font, it's bind-mounted
        # into a fontconfig-scanned path in the TeX container so XeLaTeX resolves
        # `\setmainfont{Times New Roman}` by name (no custom image needed).
        self._fonts_dir = fonts_dir
        self._fonts_host_dir = fonts_host_dir
        self._fonts_mount_target = fonts_mount_target

    def _fonts_mount_args(self) -> list[str]:
        """`-v <host_fonts>:<target>:ro` when the managed folder has fonts, else []."""
        if self._fonts_dir is None or not self._fonts_host_dir:
            return []
        try:
            has_font = self._fonts_dir.is_dir() and any(
                p.is_file() and p.suffix.lower() in (".ttf", ".otf", ".ttc") for p in self._fonts_dir.iterdir()
            )
        except OSError:
            return []
        if not has_font:
            return []
        return ["-v", f"{self._fonts_host_dir}:{self._fonts_mount_target}:ro"]

    async def run(
        self,
        project_folder: Path,
        source_file: str,
        engine: str,
        max_iterations: int,
        doc_id: str,
        compile_id: uuid.UUID,
        image: str | None = None,
        on_process_started: ProcessCallback | None = None,
    ) -> AsyncGenerator[str, None]:
        return self._stream(
            project_folder=project_folder,
            source_file=source_file,
            engine=engine,
            max_iterations=max_iterations,
            doc_id=doc_id,
            compile_id=compile_id,
            image=image or self._image,
            on_process_started=on_process_started,
        )

    async def _stream(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self,
        project_folder: Path,
        source_file: str,
        engine: str,
        max_iterations: int,
        doc_id: str,
        compile_id: uuid.UUID,
        image: str,
        on_process_started: ProcessCallback | None,
    ) -> AsyncGenerator[str, None]:
        engine_flag = _ENGINE_FLAG.get(engine)
        if engine_flag is None:
            yield f"[error] unsupported engine: {engine}"
            yield _SENTINEL_FAILED
            return

        # Engines resolve relative `\input{../foo}` against cwd, not against
        # the .tex file — templates assume cwd == .tex's directory, so we
        # chdir into it inside the container and pass only the basename.
        src_posix = PurePosixPath(source_file.replace("\\", "/"))
        src_parent = src_posix.parent.as_posix() if src_posix.parent.parts else ""
        src_basename = src_posix.name
        stem = Path(src_basename).stem
        workdir = "/work" if src_parent in ("", ".") else f"/work/{src_parent}"
        build_subdir = f".build/{doc_id}"

        host_doc_dir = project_folder if src_parent in ("", ".") else project_folder / src_parent
        host_build_dir = host_doc_dir / ".build" / doc_id
        try:
            host_build_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            yield f"[error] cannot create build dir {host_build_dir}: {exc}"
            yield _SENTINEL_FAILED
            return

        try:
            host_project_path = self._resolver.to_host(project_folder)
        except Exception as exc:
            yield f"[error] cannot resolve host path for project: {exc}"
            yield _SENTINEL_FAILED
            return

        yield (f"[compile:{compile_id}] {engine} via latexmk (max_repeat={max_iterations}, image={image})")

        cmd = [
            docker_binary(),
            "run",
            "--rm",
            "-e",
            "TEXINPUTS=/work:",
            "-e",
            "BIBINPUTS=/work:",
            "-e",
            "BSTINPUTS=/work:",
            # Ask TeX to keep "Output written on <path> (N pages" on one log
            # line. TL2023+ ignores the env override, so _extract_log_page_count
            # also unwraps the log as a fallback; kept for older images.
            "-e",
            "max_print_line=10000",
            "-v",
            f"{host_project_path}:/work:z",
            "-v",
            f"{self._cache_volume_name}:{self._cache_volume_target}",
            *self._fonts_mount_args(),
            "-w",
            workdir,
            image,
            "latexmk",
            engine_flag,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-synctex=1",
            f"-output-directory={build_subdir}",
            "-e",
            f"$max_repeat={max_iterations};",
            src_basename,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asubprocess.PIPE,
                stderr=asubprocess.STDOUT,
            )
        except OSError as exc:
            yield f"[error] docker exec failed: {exc}"
            yield _SENTINEL_FAILED
            return

        if on_process_started is not None:
            on_process_started(proc)

        assert proc.stdout is not None  # noqa: S101

        timed_out = False
        try:
            while True:
                try:
                    raw_line = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=self._idle_timeout_s,
                    )
                except asyncio.TimeoutError:
                    yield f"[error] no output for {self._idle_timeout_s:.0f}s, killing process"
                    timed_out = True
                    break
                if not raw_line:
                    break
                yield raw_line.decode("utf-8", errors="replace").rstrip()
        except asyncio.CancelledError:
            # Runner has issued cancel — make sure docker is killed before
            # re-raising or the child container keeps running with /work
            # mounted.
            await _terminate_process(proc)
            raise

        if timed_out:
            await _terminate_process(proc)
            _reset_latexmk_state(host_build_dir, stem)
            yield _SENTINEL_FAILED
            return

        await proc.wait()

        if proc.returncode != 0:
            yield f"[compile:{compile_id}] latexmk exited with code {proc.returncode}"
            # A failed run poisons latexmk's state DB: the next compile of the
            # SAME unchanged source would print "Nothing to do / gave an error
            # in previous invocation" and exit 12 without re-running the engine
            # — hiding the real error forever. Drop the DB so the next Сборка
            # starts fresh. The .log stays for inspection.
            _reset_latexmk_state(host_build_dir, stem)
            yield _SENTINEL_FAILED
            return

        yield f"[compile:{compile_id}] latexmk converged (rc=0)"

        # Atomic swap: move the freshly built PDF next to the source so the
        # existing /api/v1/projects/<id>/files/<rel>.pdf URL keeps working.
        # On failure the move is skipped and any previous PDF stays in place.
        built_pdf = host_build_dir / f"{stem}.pdf"
        final_pdf = host_doc_dir / f"{stem}.pdf"
        if not built_pdf.exists():
            yield f"[error] expected PDF not produced: {built_pdf.name}"
            yield _SENTINEL_FAILED
            return
        # On Windows the target PDF may be briefly locked by an antivirus
        # scan, the OneDrive indexer or an open viewer (WinError 32) — retry
        # a few times instead of failing an otherwise green build.
        move_error: OSError | None = None
        for attempt in range(_PDF_MOVE_ATTEMPTS):
            try:
                shutil.move(str(built_pdf), str(final_pdf))
                move_error = None
                break
            except OSError as exc:
                move_error = exc
                if attempt < _PDF_MOVE_ATTEMPTS - 1:
                    await asyncio.sleep(_PDF_MOVE_RETRY_DELAY_S)
        if move_error is not None:
            # A persistent lock (typically the PDF is open in a desktop viewer)
            # must not fail an otherwise green build: the fresh PDF stays in
            # .build, the archive picks it up from there and the app preview
            # serves the archive. Only the copy next to the sources goes stale
            # until the viewer releases it.
            yield (
                f"[warn] could not replace {final_pdf.name} next to the sources "
                f"(file is open in another program); fresh PDF kept in .build"
            )
        else:
            yield f"[compile:{compile_id}] pdf written to {final_pdf.name}"

        pages = _extract_log_page_count(host_build_dir / f"{stem}.log")
        if pages is not None:
            yield f"{_SENTINEL_PAGES}{pages}"

        counts = await self._run_texcount(host_project_path, workdir, image, src_basename)
        if counts is not None:
            words, chars = counts
            yield f"{_SENTINEL_WORDS}{words}:{chars}"
        yield _SENTINEL_DONE

    async def _run_texcount(
        self,
        host_project_path: str,
        workdir: str,
        image: str,
        src_basename: str,
    ) -> tuple[int, int] | None:
        """Prose word + character totals for the document, via texcount.

        `texcount -inc -1` prints one `text+headers+captions (...) Total` line
        and follows \\input/\\include; `-char` switches the same shape to
        characters. We sum text+headers+captions (the parts that render as
        prose — body plus headings). A separate, short `docker run` in the same
        image/working dir as latexmk, so includes resolve identically.
        Best-effort: any failure (no texcount, timeout, unparseable) → None,
        leaving the count simply absent rather than failing the build.
        """
        sep = "___HSE_TEXCOUNT_SEP___"
        # texcount has no `--` end-of-options marker (it errors on it); the
        # source is a template basename that never starts with `-`, and
        # shlex.quote guards spaces/specials for the in-container shell.
        quoted = shlex.quote(src_basename)
        script = f"texcount -inc -1 {quoted} 2>/dev/null; echo {sep}; texcount -inc -1 -char {quoted} 2>/dev/null"
        cmd = [
            docker_binary(),
            "run",
            "--rm",
            "-v",
            f"{host_project_path}:/work:z",
            "-v",
            f"{self._cache_volume_name}:{self._cache_volume_target}",
            "-w",
            workdir,
            image,
            "sh",
            "-c",
            script,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asubprocess.PIPE,
                stderr=asubprocess.STDOUT,
            )
            raw, _ = await asyncio.wait_for(proc.communicate(), timeout=self._idle_timeout_s)
        except (OSError, asyncio.TimeoutError):
            return None
        if not raw:
            return None
        words_block, _sep, chars_block = raw.decode("utf-8", errors="replace").partition(sep)
        words = _sum_texcount_total(words_block)
        chars = _sum_texcount_total(chars_block)
        if words is None or chars is None:
            return None
        return (words, chars)


def _reset_latexmk_state(build_dir: Path, stem: str) -> None:
    """Delete latexmk's per-document file database after a failed run.

    latexmk records each rule's success/failure in `<stem>.fdb_latexmk`. Left
    behind after a failure, it makes the next compile of unchanged source exit
    12 ("gave an error in previous invocation") without re-running the engine.
    Removing it forces a clean re-run; the `.log` is intentionally preserved.
    """
    with suppress(OSError):
        (build_dir / f"{stem}.fdb_latexmk").unlink(missing_ok=True)


def _sum_texcount_total(block: str) -> int | None:
    """Sum text+headers+captions from a texcount `-1` total line, or None."""
    for line in block.splitlines():
        m = _TEXCOUNT_TOTAL_RE.match(line)
        if m is not None:
            return int(m.group(1)) + int(m.group(2)) + int(m.group(3))
    return None


def _extract_log_page_count(log_path: Path) -> int | None:
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


async def _terminate_process(proc: asubprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=_PROCESS_TERMINATE_TIMEOUT_S)
    except asyncio.TimeoutError:
        with suppress(ProcessLookupError):
            proc.kill()
