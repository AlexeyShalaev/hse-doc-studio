"""Остановка облачных сборок проекта по просьбе локальной Студии: что останавливается и права."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.artifacts.entities import ArtifactError, ArtifactErrorCode
from hse_doc_studio.use_cases.artifacts.builds import CancelCloudBuildsUC, GitProjectGate


def _uc(*doc_ids: str) -> tuple[CancelCloudBuildsUC, AsyncMock]:
    locator = MagicMock()
    locator.locate = AsyncMock(return_value=(Path("/p"), MagicMock()))
    records = [MagicMock(id=uuid4(), doc_id=doc_id) for doc_id in doc_ids]
    repo = MagicMock()
    repo.list_unfinished = AsyncMock(return_value=records)
    cancel = MagicMock()
    cancel.execute = AsyncMock()
    return CancelCloudBuildsUC(locator, repo, cancel), cancel.execute


async def test__without_a_document__every_unfinished_build_is_stopped() -> None:
    uc, cancel = _uc("tz", "vkr")

    assert await uc.execute(uuid4(), None) == 2
    assert cancel.await_count == 2


async def test__one_document__only_its_build_is_stopped() -> None:
    uc, cancel = _uc("tz", "vkr")

    assert await uc.execute(uuid4(), "vkr") == 1
    assert cancel.await_args.args[0].compile_id is not None


async def test__nothing_unfinished__repeat_is_a_noop() -> None:
    uc, cancel = _uc()

    assert await uc.execute(uuid4(), None) == 0
    cancel.assert_not_awaited()


async def test__reader_without_build_right__forbidden() -> None:
    acl_repo = MagicMock()
    acl = MagicMock()
    acl.grant_for.return_value = MagicMock()
    acl_repo.load_for = AsyncMock(return_value=acl)
    actor = MagicMock()
    gate = GitProjectGate(acl_repo)

    from hse_doc_studio.use_cases.artifacts import builds

    decisions = iter([builds.Decision.allow, builds.Decision.forbidden])
    original = builds.decide
    builds.decide = lambda *_a, **_k: next(decisions)  # type: ignore[assignment]
    try:
        with pytest.raises(ArtifactError) as raised:
            await gate.require_build(actor, uuid4())
    finally:
        builds.decide = original  # type: ignore[assignment]

    assert raised.value.code is ArtifactErrorCode.forbidden
