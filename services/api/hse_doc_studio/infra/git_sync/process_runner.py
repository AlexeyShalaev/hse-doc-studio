"""Запуск дочернего процесса git: таймаут, отмена с гарантированной остановкой детей, разбор прогресса.

Это самый нижний слой сетевого git. Окружение, аргументы и секреты готовит GitRemoteRunner,
сюда они приходят уже собранными. Процесс стартует в своей группе, потому что git порождает
git-remote-https, ssh и upload-pack: при таймауте или отмене группа получает SIGTERM, а после
короткой паузы SIGKILL, и ни один потомок не остаётся висеть на сокете.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.git_sync.entities import GitResult
from hse_doc_studio.core.git_sync.protocols import ProgressCallback

_READ_CHUNK = 4096
# Хвост stderr, который сохраняется для классификатора: сообщение об ошибке стоит в конце.
_STDERR_KEEP_BYTES = 64 * 1024
_TERMINATE_GRACE_S = 3.0

# Фаза git и её доля в общей шкале 0..100. Фазы идут друг за другом, шкала не откатывается назад:
# получение объектов занимает середину, разбор дельт хвост. Неизвестные фазы процент не двигают.
_PHASES: Mapping[str, tuple[float, float]] = {
    "counting objects": (0.0, 5.0),
    "compressing objects": (5.0, 20.0),
    "receiving objects": (20.0, 85.0),
    "unpacking objects": (20.0, 85.0),
    "writing objects": (20.0, 95.0),
    "resolving deltas": (90.0, 100.0),
}
_PROGRESS_LINE = re.compile(r"^(?:remote:\s+)?(?P<phase>[A-Za-z][A-Za-z ]*?):\s+(?P<percent>\d{1,3})%")
_LINE_BREAK = re.compile(rb"[\r\n]+")


class ProcessTimeoutError(Exception):
    """Процесс не уложился в срок и убит вместе с группой."""


@dataclass(frozen=True)
class ProgressLine:
    phase: str
    # Доля внутри фазы, 0..100.
    percent: float
    # Положение на общей шкале, 0..100.
    overall: float


def parse_progress(line: str) -> ProgressLine | None:
    """Строка прогресса git (`Receiving objects:  45% (900/2000)`) или None, если это не она."""
    match = _PROGRESS_LINE.match(line.strip())
    if match is None:
        return None
    phase = match.group("phase").strip().lower()
    span = _PHASES.get(phase)
    if span is None:
        return None
    percent = min(float(match.group("percent")), 100.0)
    low, high = span
    return ProgressLine(phase, percent, low + (high - low) * percent / 100.0)


class _StderrReader:
    """Читает stderr кусками и режет по `\\r` и `\\n`: git рисует прогресс одной строкой через возврат каретки."""

    def __init__(self, on_progress: ProgressCallback | None) -> None:
        self._on_progress = on_progress
        self._kept = bytearray()
        self._best = 0.0

    @property
    def text(self) -> str:
        return bytes(self._kept[-_STDERR_KEEP_BYTES:]).decode("utf-8", errors="replace")

    async def read(self, stream: asyncio.StreamReader) -> None:
        pending = b""
        while chunk := await stream.read(_READ_CHUNK):
            pending += chunk
            *lines, pending = _LINE_BREAK.split(pending)
            for raw in lines:
                self._line(raw)
        self._line(pending)

    def _line(self, raw: bytes) -> None:
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace")
        progress = parse_progress(text)
        if progress is None:
            self._kept += raw + b"\n"
            return
        self._best = max(self._best, progress.overall)
        if self._on_progress is not None:
            self._on_progress(self._best, text.strip())


def _signal_group(process: asyncio.subprocess.Process, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        if os.name == "posix":
            os.killpg(process.pid, sig)
        elif sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()


async def _stop(process: asyncio.subprocess.Process) -> None:
    """Остановить процесс и его потомков; к возврату процесс собран, зомби не остаётся."""
    _signal_group(process, signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), _TERMINATE_GRACE_S)
    except TimeoutError:
        _signal_group(process, getattr(signal, "SIGKILL", signal.SIGTERM))
        await process.wait()


class GitProcessRunner:
    async def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        cwd: Path,
        timeout_s: float,
        on_progress: ProgressCallback | None = None,
    ) -> GitResult:
        """Выполнить команду. Не нулевой код возврата это результат, а не исключение.

        Бросает ProcessTimeoutError по истечении срока, OSError, если бинарник не запустился,
        и пробрасывает CancelledError после остановки процесса.
        """
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(env),
            cwd=cwd,
            start_new_session=os.name == "posix",
        )
        self._started(process)
        assert process.stdout is not None  # noqa: S101 — оба канала заказаны PIPE
        assert process.stderr is not None  # noqa: S101
        reader = _StderrReader(on_progress)
        try:
            async with asyncio.timeout(timeout_s):
                stdout, _, _ = await asyncio.gather(process.stdout.read(), reader.read(process.stderr), process.wait())
        except TimeoutError:
            await _stop(process)
            raise ProcessTimeoutError from None
        except BaseException:
            await asyncio.shield(_stop(process))
            raise
        returncode = process.returncode if process.returncode is not None else -1
        return GitResult(returncode=returncode, stdout=stdout, stderr=reader.text)

    def _started(self, process: asyncio.subprocess.Process) -> None:
        """Точка для наблюдения за запущенным процессом (тесты проверяют, что он не пережил операцию)."""
