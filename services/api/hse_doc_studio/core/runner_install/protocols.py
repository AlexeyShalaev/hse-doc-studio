from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from hse_doc_studio.core.runner_install.entities import (
    Capability,
    InstallStepState,
    InstallTarget,
    LocalInstance,
    LocalRunnerSpec,
)
from hse_doc_studio.core.runner_install.resources import ResourceOverrides

ProgressReporter = Callable[[str, InstallStepState, str], Awaitable[None]]


class ILocalRunnerHost(Protocol):
    """Место на этой же машине, где Студия может поставить раннер: docker рядом или кластер."""

    target: InstallTarget

    async def capability(self) -> Capability: ...

    def steps(self) -> tuple[str, ...]:
        """Ключи шагов установки по порядку (кроме общих «токен» и «регистрация»)."""
        ...

    def check_resources(self, overrides: ResourceOverrides | None) -> None:
        """Лимиты из формы вне границ хоста бросают `InvalidResourcesError`; хост без лимитов их игнорирует."""
        ...

    async def install(self, spec: LocalRunnerSpec, report: ProgressReporter) -> None: ...

    async def list_instances(self) -> list[LocalInstance]: ...

    async def remove(self, name: str) -> bool:
        """Убрать установленное из админки; False, если такого нет."""
        ...
