"""Копия сроков контрольных точек в каталоге проектов (docs/design/signing-route.md, 16.3).

Миграция `dl_01_project_deadlines` только добавляет nullable-колонку: у существующих проектов NULL (срок не задан),
откат её убирает и строк не теряет. Копию пишет `ProjectCatalogMirror`: только точки версии шаблона, с названием,
снятые сроки дают SQL NULL.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.catalog import PackSubmissionConfig, SubmissionProfile
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.catalog_sync import ProjectCatalogMirror, read_catalog_deadlines
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.factories import make_project, make_template_version
from tests.factories.pg_projects import seed_project

pytestmark = pytest.mark.pg

_REVISION = "dl_01_project_deadlines"
_PREVIOUS = "sr_11_skip"
MSK = timezone(timedelta(hours=3))


async def _deadlines(engine: AsyncEngine, project_id: UUID) -> tuple[object, bool]:
    async with engine.connect() as conn:
        row = await conn.execute(
            text("SELECT deadlines, deadlines IS NULL FROM projects WHERE id = :id"), {"id": project_id}
        )
        found = row.one()
        return found[0], found[1]


async def test__migration__adds_an_empty_column_and_rollback_keeps_projects(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine, _PREVIOUS)
    project_id = uuid4()
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO projects (id, name, workspace_path, kind, lang) VALUES (:id, 'p', :path, 'project', 'ru')"
            ),
            {"id": project_id, "path": str(project_id)},
        )

    await migrator.upgrade(pg_engine, _REVISION)

    assert await _deadlines(pg_engine, project_id) == (None, True)
    await migrator.upgrade(pg_engine)
    assert await migrator.check_drift(pg_engine) == []
    await migrator.downgrade(pg_engine, _PREVIOUS)
    async with pg_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM projects"))).scalar_one() == 1


def _templates() -> MagicMock:
    profile = SubmissionProfile(
        id="topic-approval", name={"ru": "Заявка", "en": "Topic"}, description={}, items=(), extra_items=()
    )
    templates = MagicMock()
    templates.get_version.return_value = replace(
        make_template_version(), pack_submission=PackSubmissionConfig(profiles=(profile,))
    )
    return templates


async def test__mirror__copies_known_checkpoints_with_names_and_clears_to_sql_null(
    pg_migrated_engine: AsyncEngine, tmp_path: Path
) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    project_id = await seed_project(sessions, owner_user_id=None)
    mirror = ProjectCatalogMirror(sessions, _templates())
    deadline = datetime(2026, 11, 15, 23, 59, tzinfo=MSK)
    project = replace(
        make_project(folder=tmp_path),
        id=project_id,
        deadlines={"topic-approval": deadline, "removed-in-new-version": deadline},
    )

    assert await mirror.mirror(project_id, project) is True
    copy, _ = await _deadlines(pg_migrated_engine, project_id)
    again = await mirror.mirror(project_id, project)
    cleared = await mirror.mirror(project_id, replace(project, deadlines={}))

    assert copy == {
        "topic-approval": {"deadline": "2026-11-15T23:59:00+03:00", "name": {"ru": "Заявка", "en": "Topic"}}
    }
    assert read_catalog_deadlines(copy) == (
        {"topic-approval": deadline},
        {"topic-approval": {"ru": "Заявка", "en": "Topic"}},
    )
    assert again is False
    assert cleared is True
    assert await _deadlines(pg_migrated_engine, project_id) == (None, True)
