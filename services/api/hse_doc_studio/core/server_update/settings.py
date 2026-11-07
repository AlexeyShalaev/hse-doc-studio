"""Настройки и состояние автообновления в `instance_settings`: ключи с префиксом `update.`.

Испорченное значение читается как умолчание: сломанная настройка не должна выключать проверку обновлений.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hse_doc_studio.core.server_update.entities import MaxBump, ReleaseInfo, UpdatePolicy, UpdateSettings, Verify
from hse_doc_studio.core.server_update.errors import UpdateError, UpdateErrorCode

P = "update."
KEY_RELEASES = P + "releases"
KEY_CHECKED_AT = P + "checked_at"
KEY_CHECK_ERROR = P + "check_error"
KEY_NOTIFIED = P + "notified_version"
KEY_ATTEMPT_AT = P + "attempt_at"
KEY_UPDATER_SEEN = P + "updater_seen_at"
KEY_UPDATER_VERSION = P + "updater_version"
KEY_UPDATER_CAPS = P + "updater_capabilities"
MAX_RELEASES = 30
MAX_NOTES = 12


def _enum[E](cls: type[E], raw: object, default: E) -> E:
    try:
        return cls(raw)  # type: ignore[call-arg]
    except ValueError:
        return default


def _int(raw: object, default: int) -> int:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else default


def _bool(raw: object, default: bool) -> bool:  # noqa: FBT001
    return raw if isinstance(raw, bool) else default


def settings_from(values: Mapping[str, object]) -> UpdateSettings:
    base = UpdateSettings()
    days_raw = values.get(P + "window_days")
    days = (
        tuple(sorted({d for d in days_raw if isinstance(d, int) and 0 <= d <= 6}))  # noqa: PLR2004
        if isinstance(days_raw, list)
        else base.window_days
    )
    return UpdateSettings(
        policy=_enum(UpdatePolicy, values.get(P + "policy"), base.policy),
        channel=base.channel,
        max_bump=_enum(MaxBump, values.get(P + "max_bump"), base.max_bump),
        window_days=days,
        window_start_min=_int(values.get(P + "window_start_min"), base.window_start_min),
        window_minutes=_int(values.get(P + "window_minutes"), base.window_minutes),
        backup_first=_bool(values.get(P + "backup_first"), base.backup_first),
        verify=_enum(Verify, values.get(P + "verify"), base.verify),
        notify_admins=_bool(values.get(P + "notify_admins"), base.notify_admins),
    )


def settings_to(s: UpdateSettings) -> dict[str, object]:
    return {
        P + "policy": s.policy.value,
        P + "channel": s.channel,
        P + "max_bump": s.max_bump.value,
        P + "window_days": list(s.window_days),
        P + "window_start_min": s.window_start_min,
        P + "window_minutes": s.window_minutes,
        P + "backup_first": s.backup_first,
        P + "verify": s.verify.value,
        P + "notify_admins": s.notify_admins,
    }


def validate_settings(s: UpdateSettings) -> None:
    if s.channel != "stable":
        raise UpdateError(UpdateErrorCode.invalid_input, "only the stable channel is published", field="channel")
    if not 0 <= s.window_start_min < 24 * 60:  # noqa: PLR2004
        raise UpdateError(UpdateErrorCode.invalid_input, "window start is out of range", field="window_start_min")
    if not 15 <= s.window_minutes <= 24 * 60:  # noqa: PLR2004
        raise UpdateError(UpdateErrorCode.invalid_input, "window length is 15..1440 minutes", field="window_minutes")
    if not s.window_days or any(not 0 <= d <= 6 for d in s.window_days):  # noqa: PLR2004
        raise UpdateError(UpdateErrorCode.invalid_input, "pick at least one weekday (0..6)", field="window_days")


def releases_to(releases: tuple[ReleaseInfo, ...]) -> list[dict[str, object]]:
    return [
        {"version": r.version, "date": r.date, "notes": list(r.notes[:MAX_NOTES]), "digests_url": r.digests_url}
        for r in releases[:MAX_RELEASES]
    ]


def releases_from(values: Mapping[str, object]) -> tuple[ReleaseInfo, ...]:
    raw = values.get(KEY_RELEASES)
    if not isinstance(raw, list):
        return ()
    out: list[ReleaseInfo] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("version"), str) and item["version"]:
            notes = item.get("notes")
            out.append(
                ReleaseInfo(
                    version=item["version"],
                    date=str(item.get("date") or ""),
                    notes=tuple(str(n) for n in notes) if isinstance(notes, list) else (),
                    digests_url=str(item.get("digests_url") or ""),
                )
            )
    return tuple(out)


def time_from(values: Mapping[str, object], key: str) -> datetime | None:
    raw = values.get(key)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None
