from __future__ import annotations

from typing import Any

from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.protocols import IJobHandler


class JobHandlerRegistry:
    """Обработчики не-compile видов; слайс каждого семейства регистрирует свой одной строкой."""

    def __init__(self) -> None:
        self._handlers: dict[JobKind, IJobHandler[Any]] = {}

    def register(self, kind: JobKind, handler: IJobHandler[Any]) -> None:
        if kind in self._handlers:
            raise ValueError(f"handler for job kind {kind} is already registered")
        self._handlers[kind] = handler

    def get(self, kind: JobKind) -> IJobHandler[Any]:
        try:
            return self._handlers[kind]
        except KeyError:
            raise ValueError(f"no handler registered for job kind {kind}") from None
