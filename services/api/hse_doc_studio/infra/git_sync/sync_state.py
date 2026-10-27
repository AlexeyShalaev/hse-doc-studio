"""Состояние синхронизации проекта в `<хранилище>/hse-sync.json` (порт IGitSyncStateRepository).

Файл лежит внутри хранилища git: в историю он не попадает, переезжает вместе с папкой и
никогда не уходит на удалённый репозиторий. Ключи, которых эта версия Студии не знает,
при записи сохраняются: файл мог дополнить более новая версия.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.git_sync.entities import (
    LastError,
    LastSync,
    PendingSession,
    SyncHealth,
    SyncOutcome,
    SyncState,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.merge.choices import FileResolution
from hse_doc_studio.core.git_sync.merge.drafts import resolution_from_json, resolution_to_json
from hse_doc_studio.infra.persistence.unknown_fields import Struct, preserve_unknown
from hse_doc_studio.infra.vcs.git_vcs_service import store_git_dir

logger = structlog.get_logger()

SYNC_STATE_FILE = "hse-sync.json"
SYNC_STATE_VERSION = 1

_SHAPE = Struct({"pending": Struct(), "last_error": Struct(), "last_sync": Struct()})


class JsonGitSyncStateRepository:
    def _path(self, project_folder: Path) -> Path:
        return store_git_dir(project_folder) / SYNC_STATE_FILE

    def get(self, project_folder: Path) -> SyncState | None:
        raw = _read(self._path(project_folder))
        if raw is None:
            return None
        try:
            return _state_from_json(raw)
        except (KeyError, TypeError, ValueError):
            logger.warning("git sync state unreadable", folder=str(project_folder))
            return None

    def save(self, project_folder: Path, state: SyncState) -> None:
        """Записи одного проекта вызывающий сериализует сам (блокировка папки): чтение и запись тут не атомарны."""
        path = self._path(project_folder)
        old = _read(path)
        data = _state_to_json(state)
        if old is not None:
            old["version"] = max(_int(old.get("version"), 0), SYNC_STATE_VERSION)
            data["version"] = old["version"]
            if _session_id(old.get("pending")) != _session_id(data["pending"]):
                old.pop("pending", None)
        _write(path, preserve_unknown(data, old, _SHAPE))

    def clear(self, project_folder: Path) -> None:
        self._path(project_folder).unlink(missing_ok=True)


def _read(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _session_id(pending: Any) -> str | None:
    return pending.get("session_id") if isinstance(pending, dict) else None


def _sha(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: Any, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _moment(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _state_to_json(state: SyncState) -> dict[str, Any]:
    return {
        "version": SYNC_STATE_VERSION,
        "local_branch": state.local_branch,
        "remote_branch": state.remote_branch,
        "credential_id": str(state.credential_id) if state.credential_id else None,
        "insecure_http": state.insecure_http,
        "auto_fetch": state.auto_fetch,
        "fetch_interval_s": state.fetch_interval_s,
        "shared_folder_ack": state.shared_folder_ack,
        "remote_empty": state.remote_empty,
        "adopted_unrelated": state.adopted_unrelated,
        "remote_schema_newer": state.remote_schema_newer,
        "remote_required_studio": state.remote_required_studio,
        "health": state.health.value,
        "last_fetch_at": _iso(state.last_fetch_at),
        "last_fetch_ok_at": _iso(state.last_fetch_ok_at),
        "last_error": _error_to_json(state.last_error),
        "last_sync": _sync_to_json(state.last_sync),
        "pending": _pending_to_json(state.pending),
    }


def _error_to_json(error: LastError | None) -> dict[str, Any] | None:
    if error is None:
        return None
    return {"code": error.code.value, "detail": error.detail, "at": _iso(error.at)}


def _sync_to_json(sync: LastSync | None) -> dict[str, Any] | None:
    if sync is None:
        return None
    return {
        "id": sync.id,
        "at": _iso(sync.at),
        "outcome": sync.outcome.value,
        "pulled_commits": sync.pulled_commits,
        "pushed_commits": sync.pushed_commits,
    }


def _pending_to_json(pending: PendingSession | None) -> dict[str, Any] | None:
    if pending is None:
        return None
    return {
        "session_id": pending.session_id,
        "files_total": pending.files_total,
        "files_open": pending.files_open,
        "ours": pending.ours,
        "theirs": pending.theirs,
        "base": pending.base,
        "fingerprint": pending.fingerprint,
        "drafts": {path: resolution_to_json(item) for path, item in sorted(pending.drafts.items())},
        "drafts_saved_at": _iso(pending.drafts_saved_at),
        "theirs_ref": pending.theirs_ref,
    }


def _state_from_json(raw: dict[str, Any]) -> SyncState:
    interval = raw.get("fetch_interval_s")
    return SyncState(
        local_branch=_branch(raw["local_branch"]),
        remote_branch=_branch(raw["remote_branch"]),
        credential_id=_uuid(raw.get("credential_id")),
        insecure_http=raw.get("insecure_http") is True,
        health=_enum(SyncHealth, raw.get("health"), SyncHealth.ok),
        last_fetch_at=_moment(raw.get("last_fetch_at")),
        last_fetch_ok_at=_moment(raw.get("last_fetch_ok_at")),
        last_error=_error_from_json(raw.get("last_error")),
        last_sync=_sync_from_json(raw.get("last_sync")),
        pending=_pending_from_json(raw.get("pending")),
        auto_fetch=raw.get("auto_fetch") is not False,
        fetch_interval_s=interval if isinstance(interval, int) and not isinstance(interval, bool) else None,
        shared_folder_ack=raw.get("shared_folder_ack") is True,
        remote_empty=raw.get("remote_empty") is True,
        adopted_unrelated=raw.get("adopted_unrelated") is True,
        remote_schema_newer=raw.get("remote_schema_newer") is True,
        remote_required_studio=_text(raw.get("remote_required_studio")),
    )


def _branch(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("branch name is required")
    return value


def _enum[E](kind: Callable[[Any], E], value: Any, default: E) -> E:
    try:
        return kind(value)
    except ValueError:
        return default


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(value) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def _error_from_json(raw: Any) -> LastError | None:
    if not isinstance(raw, dict) or (at := _moment(raw.get("at"))) is None:
        return None
    return LastError(
        code=_enum(GitErrorCode, raw.get("code"), GitErrorCode.git_error),
        detail=str(raw.get("detail", "")),
        at=at,
    )


def _sync_from_json(raw: Any) -> LastSync | None:
    if not isinstance(raw, dict) or (at := _moment(raw.get("at"))) is None or not raw.get("id"):
        return None
    return LastSync(
        id=str(raw["id"]),
        at=at,
        outcome=_enum(SyncOutcome, raw.get("outcome"), SyncOutcome.up_to_date),
        pulled_commits=_int(raw.get("pulled_commits"), 0),
        pushed_commits=_int(raw.get("pushed_commits"), 0),
    )


def _pending_from_json(raw: Any) -> PendingSession | None:
    if not isinstance(raw, dict) or not raw.get("session_id"):
        return None
    return PendingSession(
        session_id=str(raw["session_id"]),
        files_total=_int(raw.get("files_total"), 0),
        files_open=_int(raw.get("files_open"), 0),
        ours=_sha(raw.get("ours")),
        theirs=_sha(raw.get("theirs")),
        base=_sha(raw.get("base")),
        fingerprint=_sha(raw.get("fingerprint")),
        drafts=_drafts_from_json(raw.get("drafts")),
        drafts_saved_at=_moment(raw.get("drafts_saved_at")),
        theirs_ref=_text(raw.get("theirs_ref")),
    )


def _drafts_from_json(raw: Any) -> dict[str, FileResolution]:
    if not isinstance(raw, dict):
        return {}
    drafts = {str(path): resolution_from_json(item) for path, item in raw.items()}
    return {path: item for path, item in drafts.items() if item is not None}
