"""Чтение и отмена операции синхронизации доступны только её владельцу."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import OperationKind
from hse_doc_studio.infra.git_sync.operation_registry import InMemoryGitOperationRegistry
from hse_doc_studio.use_cases.git_sync.operations import CancelOperationUC, GetOperationUC

_BORIS = Actor.user("boris")
_ANNA = Actor.user("anna")


@pytest.fixture(autouse=True)
def _reset_actor() -> Iterator[None]:
    yield
    set_current_actor(None)


def _begin(registry: InMemoryGitOperationRegistry, actor: Actor | None) -> str:
    set_current_actor(actor)
    return registry.begin(OperationKind.clone, project_id=None, folder=None).id


async def test__owner_reads_own_operation() -> None:
    registry = InMemoryGitOperationRegistry()
    op_id = _begin(registry, _BORIS)

    assert (await GetOperationUC(registry).execute(op_id)).id == op_id


async def test__other_user_gets_not_found_on_get_and_cancel() -> None:
    registry = InMemoryGitOperationRegistry()
    op_id = _begin(registry, _BORIS)
    set_current_actor(_ANNA)

    with pytest.raises(NotFoundError):
        await GetOperationUC(registry).execute(op_id)
    with pytest.raises(NotFoundError):
        await CancelOperationUC(registry).execute(op_id)


async def test__operation_without_owner_is_open() -> None:
    registry = InMemoryGitOperationRegistry()
    op_id = _begin(registry, Actor.local())
    set_current_actor(_ANNA)

    assert (await GetOperationUC(registry).execute(op_id)).id == op_id
