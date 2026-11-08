from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from hse_doc_studio.core.runner_install import (
    Capability,
    InstallError,
    InstallStepState,
    InstallTarget,
    InvalidResourcesError,
    LocalInstance,
    LocalRunnerSpec,
    ProgressReporter,
    ResourceOverrides,
    UpgradeOutcome,
)


class FakeLocalHost:
    """Хост установки на подмене: помнит, что ему передали, и умеет упасть на заданном шаге."""

    def __init__(
        self,
        target: InstallTarget = InstallTarget.docker,
        capability: Capability | None = None,
        *,
        fail_with: InstallError | None = None,
    ) -> None:
        self.target = target
        self._capability = capability or Capability.yes()
        self.fail_with = fail_with
        self.specs: list[LocalRunnerSpec] = []
        self.checked: list[ResourceOverrides | None] = []
        self.reject_field = ""
        self.removed: list[str] = []
        self.instances: list[LocalInstance] = []
        self.upgraded: list[tuple[str, str]] = []
        self.upgrade_fail_with: InstallError | None = None
        # Держит обновление «в работе», пока тест не отпустит; и что сделать, когда новый процесс поднялся.
        self.upgrade_gate: asyncio.Event | None = None
        self.on_upgraded: Callable[[], Awaitable[None]] | None = None

    async def capability(self) -> Capability:
        return self._capability

    def check_resources(self, overrides: ResourceOverrides | None) -> None:
        self.checked.append(overrides)
        if self.reject_field and overrides is not None:
            raise InvalidResourcesError(self.reject_field, "max")

    def steps(self) -> tuple[str, ...]:
        return ("pull", "start")

    async def install(self, spec: LocalRunnerSpec, report: ProgressReporter) -> None:
        self.specs.append(spec)
        await report("pull", InstallStepState.running, "")
        if self.fail_with is not None:
            raise self.fail_with
        await report("pull", InstallStepState.done, "")
        await report("start", InstallStepState.done, "")

    def upgrade_steps(self) -> tuple[str, ...]:
        return ("pull", "recreate")

    async def upgrade(self, name: str, image: str, report: ProgressReporter) -> UpgradeOutcome:
        old = next((i.image for i in self.instances if i.name == name), "")
        await report("pull", InstallStepState.running, image)
        if self.upgrade_gate is not None:
            await self.upgrade_gate.wait()
        if self.upgrade_fail_with is not None:
            raise self.upgrade_fail_with
        await report("pull", InstallStepState.done, "")
        await report("recreate", InstallStepState.done, "")
        self.upgraded.append((name, image))
        if self.on_upgraded is not None:
            await self.on_upgraded()
        return UpgradeOutcome(old_image=old, new_image=image)

    async def list_instances(self) -> list[LocalInstance]:
        return list(self.instances)

    async def remove(self, name: str) -> bool:
        if name not in {i.name for i in self.instances}:
            return False
        self.removed.append(name)
        return True
