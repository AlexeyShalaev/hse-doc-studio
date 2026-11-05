"""Формы `/api/admin/updates` и протокола апдейтера `/api/updater/v1`."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from hse_doc_studio.api.schemas.common import StrictModel

PolicyName = Literal["off", "notify", "auto"]
MaxBumpName = Literal["patch", "minor"]
VerifyName = Literal["none", "digest", "cosign"]
RunKindName = Literal["update", "rollback"]
RunTriggerName = Literal["auto", "manual"]
RunStatusName = Literal["waiting_backup", "queued", "running", "succeeded", "rolled_back", "failed", "cancelled"]
EventLevel = Literal["info", "warn", "error"]


class UpdateSettingsBody(StrictModel):
    policy: PolicyName
    channel: Literal["stable"] = "stable"
    max_bump: MaxBumpName
    window_days: list[int] = Field(min_length=1, max_length=7)
    window_start_min: int = Field(ge=0, lt=1440)
    window_minutes: int = Field(ge=15, le=1440)
    backup_first: bool
    verify: VerifyName
    notify_admins: bool


class ReleaseOut(StrictModel):
    version: str
    date: str
    notes: list[str]
    has_digest: bool


class RunEventOut(StrictModel):
    seq: int
    at: AwareDatetime
    phase: str
    level: EventLevel
    message: str


class RunOut(StrictModel):
    id: str
    kind: RunKindName
    trigger: RunTriggerName
    status: RunStatusName
    phase: str | None
    from_version: str
    to_version: str
    from_revision: str | None
    to_revision: str | None
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    duration_s: float | None
    backup_run_id: str | None
    restore_db: bool
    db_restored: bool
    error_code: str | None
    error: str | None
    events: list[RunEventOut]


class RunPageOut(StrictModel):
    items: list[RunOut]
    total: int
    limit: int
    offset: int


class BackupsAcceptedOut(StrictModel):
    reason: str
    by_name: str
    at: AwareDatetime
    until: AwareDatetime | None


class UpdateStatusOut(StrictModel):
    settings: UpdateSettingsBody
    current_version: str
    executor: Literal["compose", "kubernetes", "none"]
    updater_online: bool
    updater_seen_at: AwareDatetime | None
    updater_version: str | None
    available: ReleaseOut | None
    auto_target: ReleaseOut | None
    releases: list[ReleaseOut]
    checked_at: AwareDatetime | None
    check_error: str | None
    in_window: bool
    next_window_at: AwareDatetime | None
    backup_destination_configured: bool
    active_run: RunOut | None
    last_run: RunOut | None
    rollback_version: str | None
    rollback_needs_restore: bool
    rollback_blocked: bool
    risk_confirmation_required: bool
    # Бэкапы отключены осознанно (самодиагностика): подтверждение риска не нужно, диалог показывает причину.
    backups_accepted: BackupsAcceptedOut | None
    manual_command: str


class StartUpdateBody(StrictModel):
    version: str | None = Field(default=None, max_length=64)
    accept_risk: bool = Field(
        default=False, description="kubernetes: подтверждение, что полного бэкапа не будет, а базу откатить нельзя."
    )


class RollbackBody(StrictModel):
    restore_db: bool = False


# ---- протокол апдейтера ----


class UpdaterPollBody(StrictModel):
    protocol: int = 1
    updater_version: str = Field(default="", max_length=64)
    busy: bool = False


class UpdaterRunSpec(StrictModel):
    run_id: str
    kind: RunKindName
    from_version: str
    to_version: str
    verify: VerifyName
    digests_url: str
    restore_db: bool


class UpdaterPollOut(StrictModel):
    run: UpdaterRunSpec | None


class UpdaterEventBody(StrictModel):
    seq: int = Field(ge=1)
    at: AwareDatetime
    phase: str = Field(max_length=32)
    level: EventLevel = "info"
    message: str = Field(default="", max_length=2000)
    status: Literal["running", "succeeded", "rolled_back", "failed", "cancelled"] | None = None
    from_revision: str | None = Field(default=None, max_length=64)
    to_revision: str | None = Field(default=None, max_length=64)
    db_restored: bool | None = None
    error_code: str | None = Field(default=None, max_length=64)


class UpdaterEventOut(StrictModel):
    status: RunStatusName
    last_seq: int
