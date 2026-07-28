from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.use_cases.compile.trigger_compile import (
    TriggerCompileInput,
    TriggerCompileUC,
    _parse_words_sentinel,
)

from tests.factories import (
    make_custom_file_override,
    make_document,
    make_document_definition,
    make_project,
    make_template_version,
)


def _make_uc(project_folder) -> TriggerCompileUC:
    project_index_repo = MagicMock()
    project_index_repo.list_known.return_value = [project_folder]
    return TriggerCompileUC(
        project_repo=MagicMock(),
        project_index_repo=project_index_repo,
        compile_repo=MagicMock(),
        template_repo=MagicMock(),
        template_service=ProjectTemplateService(),
        check_resolution_service=MagicMock(),
        check_runner=MagicMock(),
        changelog_repo=MagicMock(),
        log_bus=MagicMock(),
        settings_repo=MagicMock(),
        compile_runner=MagicMock(),
        compile_limiter=MagicMock(),
        executor=AsyncMock(),
        image_manager=AsyncMock(),
        lt_manager=AsyncMock(),
        office_manager=AsyncMock(),
        vcs_service=MagicMock(),
        vcs_locks=MagicMock(),
    )


async def test__trigger_compile__custom_file_set__short_circuits_no_docker_invocation(tmp_path) -> None:
    # A document with a custom_file override; no chosen_variant/def resolution
    # should even be attempted for source, and docker preflight (which would
    # try to invoke docker/latex) must never run.
    custom = make_custom_file_override(original_filename="ТЗ.docx", stored_path="tz/_custom/ТЗ.docx", ext=".docx")
    doc = make_document("tz", custom_file=custom)
    project = make_project(folder=tmp_path, documents=[doc])
    uc = _make_uc(tmp_path)
    uc._project_repo.get.return_value = project
    uc._template_repo.get_version.return_value = make_template_version(documents=(make_document_definition("tz"),))

    with (
        patch("hse_doc_studio.use_cases.compile.trigger_compile.regenerate_dynamic_includes") as mock_regen,
        patch("hse_doc_studio.use_cases.compile.trigger_compile.instantiate_nda") as mock_nda,
    ):
        mock_regen.return_value = None
        mock_nda.return_value = None
        uc._run_compile_task = AsyncMock()  # do not actually run the background task body

        out = await uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))
        # execute() schedules _run_compile_task as a background asyncio task
        # and returns immediately — yield once so the scheduled task actually
        # runs (and the mock records its call) before we assert on it.
        await asyncio.sleep(0)

    # Docker preflight (status/inspect) never invoked.
    uc._image_manager.docker_status.assert_not_awaited()
    uc._image_manager.inspect.assert_not_awaited()

    # The compile task was scheduled with the custom file as source,
    # needs_compile=False, custom_mode=True.
    assert uc._run_compile_task.await_args is not None
    kwargs = uc._run_compile_task.await_args.kwargs
    assert kwargs["source_file"] == "tz/_custom/ТЗ.docx"
    assert kwargs["needs_compile"] is False
    assert kwargs["custom_mode"] is True
    assert out.compile_id is not None


async def test__trigger_compile__no_custom_file__docker_preflight_runs(tmp_path) -> None:
    # Control case — a plain templated document still goes through the normal
    # docker preflight (contrast with the custom_file short-circuit above).
    doc = make_document("tz")
    project = make_project(folder=tmp_path, documents=[doc])
    uc = _make_uc(tmp_path)
    uc._project_repo.get.return_value = project
    uc._template_repo.get_version.return_value = make_template_version(documents=(make_document_definition("tz"),))
    uc._image_manager.docker_status.return_value = MagicMock(available=True)
    uc._image_manager.inspect.return_value = MagicMock()

    with (
        patch("hse_doc_studio.use_cases.compile.trigger_compile.regenerate_dynamic_includes") as mock_regen,
        patch("hse_doc_studio.use_cases.compile.trigger_compile.instantiate_nda") as mock_nda,
    ):
        mock_regen.return_value = None
        mock_nda.return_value = None
        uc._run_compile_task = AsyncMock()

        await uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))
        await asyncio.sleep(0)

    uc._image_manager.docker_status.assert_awaited_once()
    uc._image_manager.inspect.assert_awaited_once()
    kwargs = uc._run_compile_task.await_args.kwargs
    assert kwargs["source_file"] == "tz/main.tex"
    assert kwargs["needs_compile"] is True
    assert kwargs["custom_mode"] is False


def test__parse_words_sentinel__well_formed_line__roundtrips_word_and_char_counts() -> None:
    assert _parse_words_sentinel("__WORDS__:24:135") == (24, 135)


@pytest.mark.parametrize("line", ["__WORDS__:bad", "__WORDS__:24", "__WORDS__:"])
def test__parse_words_sentinel__garbage_line__returns_none_pair(line: str) -> None:
    assert _parse_words_sentinel(line) == (None, None)
