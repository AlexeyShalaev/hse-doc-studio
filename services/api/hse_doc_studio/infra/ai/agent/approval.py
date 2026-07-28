from __future__ import annotations

from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.repositories import ISettingsRepository

_SETTINGS_KEY = "agent_auto_approve_writes"


class ConfigApprovalGate:
    """IApprovalGate driven by the auto-approve flag.

    `read` tools always auto-run. `write`/`exec` tools require explicit user
    approval unless auto-approve is on. When a settings repo is supplied the
    flag is read LIVE from runtime settings (so a UI toggle takes effect without
    a restart); otherwise the static constructor value is used (tests).
    """

    def __init__(self, auto_approve_writes: bool = False, *, settings_repo: ISettingsRepository | None = None) -> None:
        self._static = auto_approve_writes
        self._settings_repo = settings_repo

    def requires_approval(self, kind: ToolKind) -> bool:
        if kind == ToolKind.read:
            return False
        return not self._auto_approve()

    def _auto_approve(self) -> bool:
        if self._settings_repo is None:
            return self._static
        return bool(self._settings_repo.get().get(_SETTINGS_KEY, self._static))
