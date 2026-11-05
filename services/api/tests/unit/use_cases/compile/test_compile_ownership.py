"""Отмена и поток лога компиляции: чужой compile_id при живой задаче не должен срабатывать."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.compile.cancel_compile import CancelCompileInput, CancelCompileUC
from hse_doc_studio.use_cases.compile.get_compile_stream import GetCompileStreamInput, GetCompileStreamUC


def _foreign_compile_setup() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Проект в URL найден, но записи с таким compile_id в нём нет; задача при этом жива в процессе."""
    locator = MagicMock()
    locator.locate = AsyncMock(return_value=(Path("/p/mine"), MagicMock()))
    locator.folder_of = AsyncMock(return_value=Path("/p/mine"))
    repo = AsyncMock()
    repo.get_for_project.return_value = None
    return locator, repo, MagicMock()


async def test__cancel_foreign_live_compile__not_found_and_task_untouched() -> None:
    locator, repo, log_stream = _foreign_compile_setup()
    dispatcher = MagicMock()
    dispatcher.is_active.return_value = True
    dispatcher.cancel = AsyncMock()
    uc = CancelCompileUC(MagicMock(), locator, repo, dispatcher, log_stream)

    with pytest.raises(NotFoundError):
        await uc.execute(CancelCompileInput(project_id=uuid.uuid4(), compile_id=uuid.uuid4()))

    dispatcher.cancel.assert_not_awaited()


async def test__stream_foreign_live_compile__no_log_leak() -> None:
    locator, repo, log_stream = _foreign_compile_setup()
    log_stream.has.return_value = True
    uc = GetCompileStreamUC(locator, repo, log_stream)

    lines = [line async for line in await uc.execute(GetCompileStreamInput(uuid.uuid4(), "d", uuid.uuid4()))]

    assert len(lines) == 1
    assert lines[0].startswith("[error]")
    log_stream.subscribe.assert_not_called()


def _own_compile(status: str) -> tuple[MagicMock, AsyncMock, MagicMock, MagicMock]:
    from hse_doc_studio.core.enums import CompileStatus

    locator = MagicMock()
    project = MagicMock()
    project.documents = []
    locator.locate = AsyncMock(return_value=(Path("/p/mine"), project))
    record = MagicMock()
    record.status = CompileStatus(status)
    record.log = "line"
    record.doc_id = "tz"
    repo = AsyncMock()
    repo.get_for_project.return_value = record
    dispatcher = MagicMock()
    dispatcher.is_active.return_value = False
    dispatcher.cancel = AsyncMock(return_value=True)
    project_repo = MagicMock()
    project_repo.get.return_value = None
    return locator, repo, dispatcher, project_repo


@pytest.mark.parametrize("status", ["pending", "running"])
async def test__cancel_untracked_unfinished__job_cancel_requested_and_record_cancelled(status: str) -> None:
    from hse_doc_studio.core.enums import CompileStatus

    locator, repo, dispatcher, project_repo = _own_compile(status)
    uc = CancelCompileUC(project_repo, locator, repo, dispatcher, MagicMock())
    compile_id = uuid.uuid4()

    out = await uc.execute(CancelCompileInput(project_id=uuid.uuid4(), compile_id=compile_id))

    dispatcher.cancel.assert_awaited_once_with(compile_id)
    assert out.record_finalised is True
    saved = repo.save.await_args.args[0]
    assert saved.status is CompileStatus.cancelled
    assert "[cancelled]" in saved.log


@pytest.mark.parametrize("status", ["success", "failure", "cancelled"])
async def test__cancel_already_finished__idempotent_noop(status: str) -> None:
    locator, repo, dispatcher, project_repo = _own_compile(status)
    uc = CancelCompileUC(project_repo, locator, repo, dispatcher, MagicMock())

    first = await uc.execute(CancelCompileInput(project_id=uuid.uuid4(), compile_id=uuid.uuid4()))
    second = await uc.execute(CancelCompileInput(project_id=uuid.uuid4(), compile_id=uuid.uuid4()))

    assert first.record_finalised is False
    assert second.record_finalised is False
    repo.save.assert_not_awaited()
    dispatcher.cancel.assert_not_awaited()
