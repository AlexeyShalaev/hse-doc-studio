from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.value_objects import ChecksOverride
from hse_doc_studio.use_cases.checks.run_checks import RunChecksInput, RunChecksUC

from tests.factories import make_check_rule


def _make_uc(
    resolved: list[tuple[object, CheckSeverity]],
    run_all_return: list[object] | None = None,
    *,
    config_disabled: list[str] | None = None,
    custom_file: object | None = None,
) -> RunChecksUC:
    uc = RunChecksUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=MagicMock(),
        template_service=MagicMock(),
        check_resolution_service=MagicMock(),
        check_runner=MagicMock(),
        lt_manager=AsyncMock(),
        settings_repo=MagicMock(),
    )
    doc = SimpleNamespace(
        id="vkr",
        def_id="vkr",
        owner=None,
        chosen_variant=None,
        checks_override=ChecksOverride(),
        custom_file=custom_file,
    )
    project = SimpleNamespace(
        documents=[doc],
        lock=SimpleNamespace(pack_id="p", template_id="t", version="1"),
        checks_override=ChecksOverride(),
        folder=Path("."),
        staffing="solo",
        authors=[],
    )
    uc._get_project_uc = AsyncMock()
    uc._get_project_uc.execute.return_value = SimpleNamespace(project=project)
    version = SimpleNamespace(
        documents=[SimpleNamespace(id="vkr", checks=ChecksOverride())],
        rules=[r for r, _ in resolved],
        checks_config=SimpleNamespace(disabled=config_disabled or []),
    )
    uc._template_repo.get_version.return_value = version
    uc._template_service.find_definition.return_value = SimpleNamespace(id="vkr", checks=ChecksOverride())
    uc._template_service.resolve_instance_source.return_value = ("main.tex", "main.pdf")
    uc._check_resolution_service.resolve.return_value = resolved
    uc._check_runner.run_all.return_value = run_all_return or []
    return uc


@pytest.mark.unit
async def test__run_checks__skips_log_parse_engine() -> None:
    resolved = [
        (make_check_rule(rule_id="r", engine=CheckEngine.regex), CheckSeverity.warn),
        (make_check_rule(rule_id="l", engine=CheckEngine.log_parse), CheckSeverity.warn),
    ]
    uc = _make_uc(resolved)
    await uc.execute(RunChecksInput(project_id=uuid4(), doc_id="vkr", include_external=False))

    passed = uc._check_runner.run_all.call_args.kwargs["rules_with_severity"]
    engines = {rule.engine for rule, _ in passed}
    assert CheckEngine.log_parse not in engines
    assert CheckEngine.regex in engines
    # log_content must be None — this path never compiles.
    assert uc._check_runner.run_all.call_args.kwargs["log_content"] is None


@pytest.mark.unit
async def test__run_checks__excludes_external_when_disabled() -> None:
    resolved = [
        (make_check_rule(rule_id="r", engine=CheckEngine.regex), CheckSeverity.warn),
        (make_check_rule(rule_id="lt", engine=CheckEngine.external), CheckSeverity.warn),
    ]
    uc = _make_uc(resolved)
    await uc.execute(RunChecksInput(project_id=uuid4(), doc_id="vkr", include_external=False))

    passed = uc._check_runner.run_all.call_args.kwargs["rules_with_severity"]
    engines = {rule.engine for rule, _ in passed}
    assert CheckEngine.external not in engines
    uc._lt_manager.ensure_running.assert_not_awaited()


@pytest.mark.unit
async def test__run_checks__starts_languagetool_when_external_included() -> None:
    resolved = [
        (make_check_rule(rule_id="lt", engine=CheckEngine.external), CheckSeverity.warn),
    ]
    uc = _make_uc(resolved)
    await uc.execute(RunChecksInput(project_id=uuid4(), doc_id="vkr", include_external=True))

    passed = uc._check_runner.run_all.call_args.kwargs["rules_with_severity"]
    assert any(rule.engine == CheckEngine.external for rule, _ in passed)
    uc._lt_manager.ensure_running.assert_awaited_once()


@pytest.mark.unit
async def test__run_checks__missing_document__raises() -> None:
    uc = _make_uc([])
    with pytest.raises(NotFoundError, match="не найден"):
        await uc.execute(RunChecksInput(project_id=uuid4(), doc_id="ghost"))


@pytest.mark.unit
async def test__run_checks__custom_file__uses_stored_path_and_sets_custom_mode() -> None:
    resolved = [
        (make_check_rule(rule_id="r", engine=CheckEngine.regex), CheckSeverity.warn),
    ]
    custom_file = SimpleNamespace(stored_path="tz/_custom/my-doc.docx", ext=".docx")
    uc = _make_uc(resolved, custom_file=custom_file)

    await uc.execute(RunChecksInput(project_id=uuid4(), doc_id="vkr", include_external=False))

    kwargs = uc._check_runner.run_all.call_args.kwargs
    assert kwargs["source_file"] == "tz/_custom/my-doc.docx"
    assert kwargs["custom_mode"] is True
    # No .tex to resolve through the pack — must not even attempt it.
    uc._template_service.resolve_instance_source.assert_not_called()


@pytest.mark.unit
async def test__run_checks__custom_file__skips_languagetool_container_start() -> None:
    resolved = [
        (make_check_rule(rule_id="lt", engine=CheckEngine.external), CheckSeverity.warn),
    ]
    custom_file = SimpleNamespace(stored_path="tz/_custom/my-doc.docx", ext=".docx")
    uc = _make_uc(resolved, custom_file=custom_file)

    await uc.execute(RunChecksInput(project_id=uuid4(), doc_id="vkr", include_external=True))

    uc._lt_manager.ensure_running.assert_not_awaited()
