"""Серверы ИИ-моделей в базе: запись на каждый шаг установки, чтение для списка и управления."""

from __future__ import annotations

import json

from sqlalchemy import delete, select

from hse_doc_studio.core.model_servers import (
    Engine,
    Exposure,
    ServerRecord,
    ServerStatus,
    StepState,
    Target,
)
from hse_doc_studio.infra.db.orm.model_servers import ModelServerRow
from hse_doc_studio.infra.db.session import SessionProvider


def _entity(row: ModelServerRow) -> ServerRecord:
    return ServerRecord(
        id=row.id,
        engine=Engine(row.engine),
        model=row.model,
        name=row.name,
        target=Target(row.target),
        credential_id=row.credential_id,
        host=row.host,
        container=row.container,
        status=ServerStatus(row.status),
        exposure=Exposure(row.exposure),
        endpoint=row.endpoint,
        provider_id=row.provider_id,
        image=row.image,
        steps={k: StepState(v) for k, v in json.loads(row.steps).items()},
        percent=row.percent,
        text=row.text,
        error=row.error,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _apply(row: ModelServerRow, rec: ServerRecord) -> None:
    row.engine = rec.engine.value
    row.model = rec.model
    row.name = rec.name
    row.target = rec.target.value
    row.credential_id = rec.credential_id
    row.host = rec.host
    row.container = rec.container
    row.status = rec.status.value
    row.exposure = rec.exposure.value
    row.endpoint = rec.endpoint
    row.provider_id = rec.provider_id
    row.image = rec.image
    row.steps = json.dumps({k: v.value for k, v in rec.steps.items()})
    row.percent = rec.percent
    row.text = rec.text[:400]
    row.error = rec.error[:400] if rec.error else None
    row.created_by = rec.created_by
    row.created_at = rec.created_at
    row.updated_at = rec.updated_at


class PostgresModelServerStore:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def save(self, record: ServerRecord) -> None:
        async with self._sessions.use() as session:
            row = await session.get(ModelServerRow, record.id)
            if row is None:
                row = ModelServerRow(id=record.id)
                session.add(row)
            _apply(row, record)

    async def get(self, server_id: str) -> ServerRecord | None:
        async with self._sessions.use() as session:
            row = await session.get(ModelServerRow, server_id)
            return None if row is None else _entity(row)

    async def list(self) -> list[ServerRecord]:
        async with self._sessions.use() as session:
            rows = (await session.execute(select(ModelServerRow).order_by(ModelServerRow.created_at))).scalars()
            return [_entity(row) for row in rows]

    async def delete(self, server_id: str) -> None:
        async with self._sessions.use() as session:
            await session.execute(delete(ModelServerRow).where(ModelServerRow.id == server_id))
