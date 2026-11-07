"""Серверы ИИ-моделей в Postgres: запись шагов, чтение, обновление, удаление; секретов в строке нет."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from hse_doc_studio.core.model_servers import (
    Engine,
    Exposure,
    ServerRecord,
    ServerStatus,
    StepState,
    Target,
)
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.model_servers import PostgresModelServerStore
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

_NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def _record(server_id: str = "a" * 32) -> ServerRecord:
    return ServerRecord(
        id=server_id,
        engine=Engine.vllm,
        model="Qwen/Qwen3-4B",
        name="Лабораторный vLLM",
        target=Target.ssh,
        credential_id="c" * 32,
        host="srv.example.org",
        container="hse-ms-aaaaaaaa",
        status=ServerStatus.installing,
        exposure=Exposure.localhost,
        endpoint=None,
        provider_id=None,
        image="vllm/vllm-openai:v0.32.0",
        steps={"container": StepState.running, "provider": StepState.skipped},
        percent=40,
        text="pulling",
        error=None,
        created_by="boss",
        created_at=_NOW,
        updated_at=_NOW,
    )


@pytest_asyncio.fixture
async def store(pg_migrated_engine: AsyncEngine) -> PostgresModelServerStore:
    return PostgresModelServerStore(SessionProvider(create_sessionmaker(pg_migrated_engine)))


async def test__roundtrip__every_field_and_step_states(store: PostgresModelServerStore) -> None:
    await store.save(_record())

    got = await store.get("a" * 32)

    assert got == _record()


async def test__save__updates_existing_row_in_place(store: PostgresModelServerStore) -> None:
    await store.save(_record())
    await store.save(replace(_record(), status=ServerStatus.running, percent=100, endpoint="http://x:8000"))

    [only] = await store.list()

    assert only.status is ServerStatus.running
    assert only.percent == 100
    assert only.endpoint == "http://x:8000"


async def test__delete__removes_the_row_and_missing_is_none(store: PostgresModelServerStore) -> None:
    await store.save(_record())
    await store.delete("a" * 32)
    await store.delete("a" * 32)

    assert await store.get("a" * 32) is None
    assert await store.list() == []


async def test__text_and_error_are_clipped_to_column_size(store: PostgresModelServerStore) -> None:
    await store.save(replace(_record(), text="x" * 1000, error="e" * 1000))

    got = await store.get("a" * 32)

    assert got is not None
    assert len(got.text) == 400
    assert got.error is not None
    assert len(got.error) == 400
