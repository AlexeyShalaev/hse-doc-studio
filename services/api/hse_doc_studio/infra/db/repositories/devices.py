"""Подключённые Студии в Postgres: по строке на устройство человека, отчёт лежит в JSONB."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.devices.entities import (
    ConnectedDevice,
    DeviceActivity,
    DeviceReport,
    EndpointReport,
    PdfReport,
    ProjectReport,
    RunnerReport,
    SyncCode,
    os_of,
)
from hse_doc_studio.infra.db.orm.devices import ConnectedDeviceRow
from hse_doc_studio.infra.db.session import SessionProvider


class PostgresDeviceRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def upsert(self, device: ConnectedDevice) -> None:
        report = device.report
        values: dict[str, Any] = {
            "name": report.name,
            "version": report.version,
            "os": report.os.value,
            "activity": report.activity.value,
            "last_seen_at": device.last_seen_at,
            "token_id": device.token_id,
            "report": report_to_json(report),
            "project_ids": [str(p.project_id) for p in report.projects],
        }
        stmt = pg_insert(ConnectedDeviceRow).values(
            user_id=device.user_id, device_id=device.device_id, first_seen_at=device.first_seen_at, **values
        )
        async with self._sessions.use() as session:
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[ConnectedDeviceRow.user_id, ConnectedDeviceRow.device_id], set_=values
                )
            )

    async def list_for_user(self, user_id: str) -> list[ConnectedDevice]:
        stmt = (
            select(ConnectedDeviceRow)
            .where(ConnectedDeviceRow.user_id == user_id)
            .order_by(ConnectedDeviceRow.last_seen_at.desc(), ConnectedDeviceRow.device_id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_entity(row) for row in rows]

    async def get(self, user_id: str, device_id: str) -> ConnectedDevice | None:
        stmt = select(ConnectedDeviceRow).where(
            ConnectedDeviceRow.user_id == user_id, ConnectedDeviceRow.device_id == device_id
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return None if row is None else _to_entity(row)

    async def list_for_project(self, project_id: UUID) -> list[ConnectedDevice]:
        stmt = (
            select(ConnectedDeviceRow)
            .where(ConnectedDeviceRow.project_ids.contains([str(project_id)]))
            .order_by(ConnectedDeviceRow.last_seen_at.desc(), ConnectedDeviceRow.user_id, ConnectedDeviceRow.device_id)
            .limit(500)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_entity(row) for row in rows]

    async def delete(self, user_id: str, device_id: str) -> bool:
        stmt = delete(ConnectedDeviceRow).where(
            ConnectedDeviceRow.user_id == user_id, ConnectedDeviceRow.device_id == device_id
        )
        async with self._sessions.use() as session:
            result = await session.execute(stmt)
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def purge_older_than(self, horizon: datetime) -> int:
        async with self._sessions.use() as session:
            result = await session.execute(delete(ConnectedDeviceRow).where(ConnectedDeviceRow.last_seen_at < horizon))
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


def report_to_json(report: DeviceReport) -> dict[str, Any]:
    return {
        "runner": None
        if report.runner is None
        else {
            "runner_id": report.runner.runner_id,
            "state": report.runner.state,
            "running_jobs": report.runner.running_jobs,
        },
        "endpoints": [
            {"name": e.name, "flavor": e.flavor, "reachable": e.reachable, "models": list(e.models)}
            for e in report.endpoints
        ],
        "projects": [
            {
                "project_id": str(p.project_id),
                "sync": p.sync.value,
                "ahead": p.ahead,
                "behind": p.behind,
                "last_sync_at": p.last_sync_at.isoformat() if p.last_sync_at else None,
                "auto_sync": p.auto_sync,
                "pdf": None
                if p.pdf is None
                else {"doc_id": p.pdf.doc_id, "at": p.pdf.at.isoformat(), "ok": p.pdf.ok, "code": p.pdf.code},
            }
            for p in report.projects
        ],
    }


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def report_from_json(row: ConnectedDeviceRow) -> DeviceReport:
    data: dict[str, Any] = row.report or {}
    runner = data.get("runner")
    return DeviceReport(
        device_id=row.device_id,
        name=row.name,
        version=row.version,
        os=os_of(row.os),
        activity=DeviceActivity(row.activity),
        runner=None
        if not runner
        else RunnerReport(
            runner_id=runner.get("runner_id"),
            state=runner.get("state"),
            running_jobs=int(runner.get("running_jobs", 0)),
        ),
        endpoints=tuple(
            EndpointReport(
                name=e["name"], flavor=e["flavor"], reachable=e.get("reachable"), models=tuple(e.get("models", ()))
            )
            for e in data.get("endpoints", [])
        ),
        projects=tuple(
            ProjectReport(
                project_id=UUID(p["project_id"]),
                sync=SyncCode(p["sync"]),
                ahead=int(p.get("ahead", 0)),
                behind=int(p.get("behind", 0)),
                last_sync_at=_dt(p.get("last_sync_at")),
                auto_sync=bool(p.get("auto_sync", False)),
                pdf=None
                if not p.get("pdf")
                else PdfReport(
                    doc_id=p["pdf"]["doc_id"],
                    at=datetime.fromisoformat(p["pdf"]["at"]),
                    ok=bool(p["pdf"]["ok"]),
                    code=p["pdf"].get("code"),
                ),
            )
            for p in data.get("projects", [])
        ),
    )


def _to_entity(row: ConnectedDeviceRow) -> ConnectedDevice:
    report = report_from_json(row)
    return ConnectedDevice(
        user_id=row.user_id,
        device_id=row.device_id,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        report=report,
        token_id=row.token_id,
        project_ids=tuple(p.project_id for p in report.projects),
    )
