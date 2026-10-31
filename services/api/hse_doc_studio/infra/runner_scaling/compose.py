"""Оркестратор через `docker compose up --scale`: команда без shell, с таймаутом.

Нужен docker CLI с доступом к демону там, где крутится api (обычно рядом с compose-установкой). Уменьшение
выбирает контейнер сам; раннер завершается по SIGTERM и успевает сказать серверу `/offline`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from hse_doc_studio.core.jobs.autoscale import OrchestratorError, ScaleRequest

CommandRunner = Callable[[Sequence[str], float], Awaitable[tuple[int, str]]]


async def run_command(argv: Sequence[str], timeout_s: float) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except OSError as exc:
        raise OrchestratorError(f"cannot run {argv[0]}: {exc.strerror or type(exc).__name__}") from exc
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise OrchestratorError(f"{argv[0]} timed out after {timeout_s:g} s") from exc
    return proc.returncode or 0, out.decode(errors="replace")


class ComposeOrchestrator:
    def __init__(
        self,
        service: str,
        *,
        project: str | None = None,
        compose_file: str | None = None,
        timeout_s: float = 120.0,
        runner: CommandRunner = run_command,
    ) -> None:
        self._service = service
        self._project = project
        self._file = compose_file
        self._timeout = timeout_s
        self._run = runner

    def _base(self) -> list[str]:
        argv = ["docker", "compose"]
        if self._project:
            argv += ["-p", self._project]
        if self._file:
            argv += ["-f", self._file]
        return argv

    def scale_argv(self, desired: int) -> list[str]:
        return [
            *self._base(),
            "up",
            "-d",
            "--no-recreate",
            "--no-deps",
            "--scale",
            f"{self._service}={desired}",
            self._service,
        ]

    async def scale_to(self, request: ScaleRequest) -> None:
        code, output = await self._run(self.scale_argv(request.desired), self._timeout)
        if code != 0:
            raise OrchestratorError(f"docker compose exited with {code}: {output.strip()[-300:]}")

    async def current(self) -> int | None:
        code, output = await self._run([*self._base(), "ps", "--status", "running", "-q", self._service], self._timeout)
        return len([line for line in output.splitlines() if line.strip()]) if code == 0 else None
