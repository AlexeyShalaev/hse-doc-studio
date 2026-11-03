"""Узкий порт Kubernetes API, которого хватает исполнителю: поды, лог и exec."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import IO, Protocol

PodManifest = Mapping[str, object]


class KubeApiError(Exception):
    """Ответ API с ошибкой или обрыв связи с ним; `status` это HTTP-код, если он был."""

    def __init__(self, message: str, *, status: int | None = None, reason: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


@dataclass(frozen=True)
class PodState:
    """То, что исполнитель читает из `status` пода."""

    phase: str
    reason: str = ""
    message: str = ""
    container_running: bool = False
    waiting_reason: str = ""
    waiting_message: str = ""
    terminated_reason: str = ""
    terminated_exit_code: int | None = None
    unschedulable: str = ""


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stderr: str = ""


class IKubeApi(Protocol):
    async def create_pod(self, namespace: str, manifest: PodManifest) -> None: ...

    async def read_pod(self, namespace: str, name: str) -> PodState | None:
        """`None`, если пода нет."""
        ...

    async def delete_pod(self, namespace: str, name: str) -> None:
        """Удаляет сразу (grace 0); отсутствующий под не ошибка."""
        ...

    async def list_pods(self, namespace: str, label_selector: str) -> list[str]:
        """Имена подов по селектору меток."""
        ...

    def stream_log(self, namespace: str, name: str, container: str, since_time: str | None) -> AsyncIterator[str]:
        """Строки лога с метками времени (`timestamps=true`), пока контейнер пишет или связь не оборвётся."""
        ...

    async def exec(  # noqa: PLR0913
        self,
        namespace: str,
        name: str,
        container: str,
        command: Sequence[str],
        *,
        stdin: IO[bytes] | None = None,
        stdout: Callable[[bytes], None] | None = None,
    ) -> ExecResult:
        """Команда в контейнере; `stdin` читается до конца и передаётся, stdout отдаётся кусками в `stdout`."""
        ...

    async def aclose(self) -> None: ...
