from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest
from hse_doc_studio.infra.git_sync.process_runner import (
    GitProcessRunner,
    ProcessTimeoutError,
    parse_progress,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="process groups and sh are posix-only")

_PY = sys.executable
_ENV = {"PATH": os.environ.get("PATH", "")}


class _Recording(GitProcessRunner):
    def __init__(self) -> None:
        self.processes: list[asyncio.subprocess.Process] = []

    def _started(self, process: asyncio.subprocess.Process) -> None:
        self.processes.append(process)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _gone(pid: int, within_s: float = 3.0) -> bool:
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        await asyncio.sleep(0.05)
    return False


def _sleeper_script(pid_file: Path) -> list[str]:
    """Родитель порождает внука и ждёт; оба пишут pid в файл: проверяем, что группа убита целиком."""
    script = f"sleep 60 & echo $! > {pid_file}; wait"
    return ["sh", "-c", script]


async def test__run__success__returns_stdout_stderr_and_code(tmp_path: Path) -> None:
    result = await GitProcessRunner().run(
        [_PY, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"],
        env=_ENV,
        cwd=tmp_path,
        timeout_s=10,
    )

    assert result.returncode == 3
    assert result.stdout.strip() == b"out"
    assert result.stderr.strip() == "err"


async def test__run__missing_binary__raises_os_error(tmp_path: Path) -> None:
    with pytest.raises(OSError):  # noqa: PT011
        await GitProcessRunner().run(["definitely-not-a-binary-xyz"], env=_ENV, cwd=tmp_path, timeout_s=5)


async def test__run__stdin_is_closed__child_reading_stdin_does_not_hang(tmp_path: Path) -> None:
    result = await GitProcessRunner().run(
        [_PY, "-c", "import sys; sys.stdout.write(repr(sys.stdin.read()))"], env=_ENV, cwd=tmp_path, timeout_s=10
    )

    assert result.stdout == b"''"


async def test__run__timeout__kills_whole_process_group(tmp_path: Path) -> None:
    runner = _Recording()
    pid_file = tmp_path / "grandchild.pid"

    with pytest.raises(ProcessTimeoutError):
        await runner.run(_sleeper_script(pid_file), env=_ENV, cwd=tmp_path, timeout_s=0.5)

    parent = runner.processes[0]
    grandchild = int(pid_file.read_text())
    assert parent.returncode is not None
    assert await _gone(grandchild)


async def test__run__cancel__kills_whole_process_group_and_reraises(tmp_path: Path) -> None:
    runner = _Recording()
    pid_file = tmp_path / "grandchild.pid"
    task = asyncio.create_task(runner.run(_sleeper_script(pid_file), env=_ENV, cwd=tmp_path, timeout_s=60))
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text().strip():
            break
        await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runner.processes[0].returncode is not None
    assert await _gone(int(pid_file.read_text()))


async def test__run__child_ignoring_sigterm__is_killed_after_grace(tmp_path: Path) -> None:
    runner = _Recording()
    script = (
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('up', flush=True); time.sleep(60)"
    )

    started = time.monotonic()
    with pytest.raises(ProcessTimeoutError):
        await runner.run([_PY, "-c", script], env=_ENV, cwd=tmp_path, timeout_s=0.5)

    assert runner.processes[0].returncode is not None
    assert time.monotonic() - started < 10


async def test__run__progress_lines_split_on_carriage_return__reported_monotonic(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        "sys.stderr.write('Receiving objects:  10% (1/10)\\rReceiving objects:  50% (5/10)\\r')\n"
        "sys.stderr.write('Receiving objects: 100% (10/10), done.\\n')\n"
        "sys.stderr.write('Resolving deltas:  40% (2/5)\\rResolving deltas: 100% (5/5), done.\\n')\n"
        "sys.stderr.write('fatal: something happened\\n')\n"
    )
    seen: list[tuple[float | None, str]] = []

    result = await GitProcessRunner().run(
        [_PY, "-c", script], env=_ENV, cwd=tmp_path, timeout_s=10, on_progress=lambda p, line: seen.append((p, line))
    )

    percents = [p for p, _ in seen if p is not None]
    assert len(percents) == 5
    assert percents == sorted(percents)
    assert 0 < percents[0] < percents[2] <= 85 < percents[-1] <= 100
    assert seen[0][1] == "Receiving objects:  10% (1/10)"
    assert result.stderr == "fatal: something happened\n"


async def test__run__progress_never_goes_back_when_a_later_phase_starts_lower(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        "sys.stderr.write('Writing objects: 100% (4/4), done.\\n')\n"
        "sys.stderr.write('Resolving deltas: 0% (0/1)\\n')\n"
    )
    seen: list[float | None] = []

    await GitProcessRunner().run(
        [_PY, "-c", script], env=_ENV, cwd=tmp_path, timeout_s=10, on_progress=lambda p, _line: seen.append(p)
    )

    assert seen == sorted(seen, key=lambda value: value or 0.0)


async def test__run__long_stderr__keeps_only_the_tail(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        "for i in range(20000):\n"
        "    sys.stderr.write(f'noise line number {i}\\n')\n"
        "sys.stderr.write('the end\\n')\n"
    )

    result = await GitProcessRunner().run([_PY, "-c", script], env=_ENV, cwd=tmp_path, timeout_s=20)

    assert len(result.stderr) <= 64 * 1024
    assert result.stderr.endswith("the end\n")


@pytest.mark.parametrize(
    ("line", "phase", "percent"),
    [
        ("Receiving objects:  45% (900/2000)", "receiving objects", 45.0),
        ("remote: Counting objects:  50% (1/2)", "counting objects", 50.0),
        ("Resolving deltas: 100% (5/5), done.", "resolving deltas", 100.0),
        ("Unpacking objects: 100% (3/3), 300 bytes | 100.00 KiB/s, done.", "unpacking objects", 100.0),
        ("Writing objects:   7% (1/14)", "writing objects", 7.0),
    ],
)
def test__parse_progress__known_phases__phase_and_percent(line: str, phase: str, percent: float) -> None:
    parsed = parse_progress(line)

    assert parsed is not None
    assert (parsed.phase, parsed.percent) == (phase, percent)
    assert 0 <= parsed.overall <= 100


@pytest.mark.parametrize(
    "line",
    [
        "fatal: couldn't find remote ref refs/heads/x",
        "remote: Enumerating objects: 5, done.",
        "Filtering content:  30% (1/3)",
        "warning: 100% sure this is not progress",
        "",
    ],
)
def test__parse_progress__other_text__none(line: str) -> None:
    assert parse_progress(line) is None


def test__parse_progress__phases_are_ordered_on_the_overall_scale() -> None:
    counting = parse_progress("Counting objects: 100% (3/3)")
    receiving = parse_progress("Receiving objects: 100% (3/3)")
    resolving = parse_progress("Resolving deltas: 100% (3/3)")

    assert counting is not None
    assert receiving is not None
    assert resolving is not None
    assert counting.overall < receiving.overall < resolving.overall
