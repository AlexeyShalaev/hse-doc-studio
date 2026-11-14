"""Состояние Студии шаблонов локальной установки: `data_dir/pack-studio/workspaces.json` и выбор «раздел включён».

Человек в локальной установке один, поэтому владельца у пространства нет (`owner_id` None) и фильтра по нему тоже.
Запись атомарная: временный файл рядом и замена.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.pack_studio.entities import PackWorkspace, WorkspaceError, WorkspaceKind, WorkspaceState
from hse_doc_studio.core.repositories import ISettingsRepository

logger = structlog.get_logger()

_FILE_VERSION = 1
SECTION_SETTING_KEY = "pack_studio_enabled"
# Псевдоним: внутри класса имя `list` занято методом и в аннотациях означало бы его.
_Workspaces = list[PackWorkspace]


def _dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _to_record(ws: PackWorkspace) -> dict[str, Any]:
    return {
        "id": str(ws.id),
        "kind": ws.kind.value,
        "label": ws.label,
        "packs_path": ws.packs_path,
        "state": ws.state.value,
        "remote_url": ws.remote_url,
        "credential_id": None if ws.credential_id is None else str(ws.credential_id),
        "insecure_http": ws.insecure_http,
        "base_branch": ws.base_branch,
        "base_sha": ws.base_sha,
        "fetched_at": _iso(ws.fetched_at),
        "work_branch": ws.work_branch,
        "pr_url": ws.pr_url,
        "pr_number": ws.pr_number,
        "ci_status": ws.ci_status,
        "folder": ws.folder,
        "error": None if ws.error is None else {"code": ws.error.code, "detail": ws.error.detail},
        "created_at": _iso(ws.created_at),
        "updated_at": _iso(ws.updated_at),
    }


def _from_record(raw: dict[str, Any]) -> PackWorkspace:
    error = raw.get("error")
    credential = raw.get("credential_id")
    created = _dt(raw.get("created_at")) or datetime.now(timezone.utc)
    return PackWorkspace(
        id=UUID(str(raw["id"])),
        owner_id=None,
        kind=WorkspaceKind(raw["kind"]),
        label=str(raw.get("label") or ""),
        packs_path=str(raw.get("packs_path") or "."),
        created_at=created,
        updated_at=_dt(raw.get("updated_at")) or created,
        state=WorkspaceState(raw.get("state", WorkspaceState.ready.value)),
        remote_url=raw.get("remote_url"),
        credential_id=UUID(credential) if isinstance(credential, str) else None,
        insecure_http=bool(raw.get("insecure_http", False)),
        base_branch=raw.get("base_branch"),
        base_sha=raw.get("base_sha"),
        fetched_at=_dt(raw.get("fetched_at")),
        work_branch=raw.get("work_branch"),
        pr_url=raw.get("pr_url"),
        pr_number=raw.get("pr_number") if isinstance(raw.get("pr_number"), int) else None,
        ci_status=raw.get("ci_status"),
        folder=raw.get("folder"),
        error=WorkspaceError(str(error["code"]), str(error.get("detail", "")))
        if isinstance(error, dict) and error.get("code")
        else None,
    )


class JsonPackWorkspaceRepository:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "pack-studio" / "workspaces.json"
        self._lock = threading.Lock()

    async def list(self, owner_id: str | None) -> _Workspaces:
        return sorted(self._read(), key=lambda ws: (ws.created_at, str(ws.id)))

    async def get(self, workspace_id: UUID, owner_id: str | None) -> PackWorkspace | None:
        return next((ws for ws in self._read() if ws.id == workspace_id), None)

    async def count(self, owner_id: str | None) -> int:
        return len(self._read())

    async def add(self, workspace: PackWorkspace) -> None:
        with self._lock:
            items = self._read()
            items.append(replace(workspace, owner_id=None))
            self._write(items)

    async def update(self, workspace: PackWorkspace) -> None:
        with self._lock:
            items = self._read()
            if not any(ws.id == workspace.id for ws in items):
                return
            self._write([replace(workspace, owner_id=None) if ws.id == workspace.id else ws for ws in items])

    async def delete(self, workspace_id: UUID, owner_id: str | None) -> bool:
        with self._lock:
            items = self._read()
            kept = [ws for ws in items if ws.id != workspace_id]
            if len(kept) == len(items):
                return False
            self._write(kept)
            return True

    def _read(self) -> _Workspaces:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            logger.warning("pack studio: workspaces.json is unreadable", path=str(self._path), exc=str(exc))
            return []
        items: _Workspaces = []
        for raw in data.get("workspaces", []) if isinstance(data, dict) else []:
            try:
                items.append(_from_record(raw))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("pack studio: workspace record skipped", exc=str(exc))
        return items

    def _write(self, items: _Workspaces) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            {"version": _FILE_VERSION, "workspaces": [_to_record(ws) for ws in items]}, ensure_ascii=False, indent=2
        )
        handle, name = tempfile.mkstemp(prefix="workspaces.", suffix=".tmp", dir=self._path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(body)
            os.replace(name, self._path)
        finally:
            Path(name).unlink(missing_ok=True)


class LocalSectionStore:
    """Выбор «Инструменты автора шаблонов» в Настройках локальной Студии (`config.json`)."""

    def __init__(self, settings: ISettingsRepository) -> None:
        self._settings = settings

    async def get(self) -> bool | None:
        value = (await self._settings.get()).get(SECTION_SETTING_KEY)
        return value if isinstance(value, bool) else None

    async def set(self, enabled: bool) -> None:
        current = await self._settings.get()
        await self._settings.save({**current, SECTION_SETTING_KEY: enabled})
