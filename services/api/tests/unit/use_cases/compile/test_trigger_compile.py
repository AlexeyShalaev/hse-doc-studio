from __future__ import annotations

import uuid
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.core.compile.errors import ImageMissingError
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity, CompileStatus, DocumentStatus, Lang
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.entities import CompileJobPayload, JobSpec, compile_payload_of
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from hse_doc_studio.core.jobs.protocols import IJobHooks
from hse_doc_studio.core.jobs.runner_fit import PoolState, RunnerFit, RunnerGapReason
from hse_doc_studio.core.services import CheckResolutionService, ProjectTemplateService
from hse_doc_studio.core.value_objects import ChecksOverride
from hse_doc_studio.infra.persistence.project_locator import LocalProjectLocator
from hse_doc_studio.use_cases.compile.compile_job_hooks import CompileJobHooks
from hse_doc_studio.use_cases.compile.trigger_compile import TriggerCompileInput, TriggerCompileUC

from tests.factories import (
    make_check_rule,
    make_custom_file_override,
    make_document,
    make_document_definition,
    make_project,
    make_template_version,
)


class FakeJobDispatcher:
    """Записывает вызовы в общий журнал событий; сами задачи не выполняет."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.preflight_error: Exception | None = None
        # Отказ только для этих документов: «Собрать все», где часть документов собрать некому.
        self.refuse_docs: dict[str, Exception] = {}
        self.preflighted: list[JobSpec] = []
        self.submitted: list[tuple[JobSpec, IJobHooks]] = []

    async def preflight(self, spec: JobSpec) -> None:
        self.events.append("preflight")
        self.preflighted.append(spec)
        if self.preflight_error is not None:
            raise self.preflight_error
        refusal = self.refuse_docs.get(compile_payload_of(spec).doc_id)
        if refusal is not None:
            raise refusal

    def submit(self, spec: JobSpec, hooks: IJobHooks) -> None:
        self.events.append("submit")
        self.submitted.append((spec, hooks))


class FakeMaterializer:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def regenerate_dynamic_includes(self, project: Project, version: object) -> None:
        self.events.append("regenerate_dynamic_includes")

    def instantiate_nda(self, project: Project, version: object) -> list[str]:
        self.events.append("instantiate_nda")
        return []


class Harness:
    def __init__(self, project_folder) -> None:
        self.events: list[str] = []
        self.dispatcher = FakeJobDispatcher(self.events)
        self.materializer = FakeMaterializer(self.events)
        self.project_repo = MagicMock()
        self.compile_repo = AsyncMock()
        self.compile_repo.save.side_effect = lambda record: self.events.append(f"save:{record.status}")
        self.template_repo = MagicMock()
        project_index_repo = MagicMock()
        project_index_repo.list_known.return_value = [project_folder]
        self.uc = TriggerCompileUC(
            project_repo=self.project_repo,
            locator=LocalProjectLocator(project_index_repo, self.project_repo),
            compile_repo=self.compile_repo,
            template_repo=self.template_repo,
            template_service=ProjectTemplateService(),
            check_resolution_service=CheckResolutionService(),
            changelog_repo=MagicMock(),
            dispatcher=self.dispatcher,
            materializer=self.materializer,
            artifacts=MagicMock(),
            vcs_service=MagicMock(),
            vcs_locks=MagicMock(),
        )

    def given(self, project: Project, **version_kwargs: object) -> None:
        self.project_repo.get.return_value = project
        self.template_repo.get_version.return_value = make_template_version(**version_kwargs)

    @property
    def spec(self) -> JobSpec:
        assert len(self.dispatcher.submitted) == 1
        return self.dispatcher.submitted[0][0]

    @property
    def payload(self) -> CompileJobPayload:
        return compile_payload_of(self.spec)


async def test__trigger_compile__custom_file_set__short_circuits_no_docker_invocation(tmp_path) -> None:
    custom = make_custom_file_override(original_filename="ТЗ.docx", stored_path="tz/_custom/ТЗ.docx", ext=".docx")
    doc = make_document("tz", custom_file=custom)
    h = Harness(tmp_path)
    h.given(make_project(folder=tmp_path, documents=[doc]), documents=(make_document_definition("tz"),))

    out = await h.uc.execute(TriggerCompileInput(project_id=h.project_repo.get.return_value.id, doc_id="tz"))

    assert h.payload.source_file == "tz/_custom/ТЗ.docx"
    assert h.payload.needs_compile is False
    assert h.payload.custom_mode is True
    assert h.spec.id == out.compile_id
    assert h.spec.tags == frozenset({"office"})


async def test__trigger_compile__no_custom_file__plain_document_spec(tmp_path) -> None:
    doc = make_document("tz")
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[doc])
    h.given(project, documents=(make_document_definition("tz"),))

    await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))

    assert len(h.dispatcher.preflighted) == 1
    assert h.payload.source_file == "tz/main.tex"
    assert h.payload.needs_compile is True
    assert h.payload.custom_mode is False
    assert h.payload.doc_id == "tz"
    assert h.payload.def_id == "tz"
    assert h.spec.kind is JobKind.compile
    assert h.spec.tags == frozenset({"tex"})
    assert h.spec.project_id == project.id
    assert h.spec.local_root == tmp_path
    assert h.spec.actor.is_local


async def test__trigger_compile__custom_file__preflight_still_goes_through_dispatcher(tmp_path) -> None:
    # Решение «нужен ли docker» принимает раннер по needs_compile, а не use case.
    custom = make_custom_file_override(original_filename="ТЗ.docx", stored_path="tz/_custom/ТЗ.docx", ext=".docx")
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz", custom_file=custom)])
    h.given(project, documents=(make_document_definition("tz"),))

    await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))

    assert h.dispatcher.preflighted == [h.spec]
    assert h.payload.needs_compile is False


async def test__trigger_compile__order__materialize_then_preflight_then_pending_then_submit(tmp_path) -> None:
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h.given(project, documents=(make_document_definition("tz"),))

    await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))

    assert h.events == [
        "regenerate_dynamic_includes",
        "instantiate_nda",
        "preflight",
        f"save:{CompileStatus.pending}",
        "submit",
    ]


async def test__trigger_compile__preflight_refuses__failed_record_with_reason_nothing_submitted(tmp_path) -> None:
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h.given(project, documents=(make_document_definition("tz"),))
    h.dispatcher.preflight_error = ImageMissingError("texlive:latest")

    with pytest.raises(ImageMissingError):
        await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))

    (record,) = [call.args[0] for call in h.compile_repo.save.call_args_list]
    assert record.status is CompileStatus.failure
    assert (record.error_code, record.error_detail) == ("image_missing", "Docker image not installed: texlive:latest")
    assert record.log.startswith("[error] image_missing: ")
    doc = next(d for d in h.project_repo.save.call_args.args[0].documents if d.id == "tz")
    assert (doc.status, doc.last_compile_id) == (DocumentStatus.err, record.id)
    assert h.dispatcher.submitted == []


async def test__trigger_compile__no_runner__failed_record_with_no_runners_code(tmp_path) -> None:
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h.given(project, documents=(make_document_definition("tz"),))
    h.dispatcher.preflight_error = NoRunnerAvailableError(frozenset({"tex"}))

    with pytest.raises(NoRunnerAvailableError):
        await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))

    (record,) = [call.args[0] for call in h.compile_repo.save.call_args_list]
    assert (record.status, record.error_code) == (CompileStatus.failure, "no_runners")


async def test__trigger_compile__build_all_with_paused_office_runner__only_that_document_excluded(tmp_path) -> None:
    # «Собрать все» ставит документы по одному: презентации собрать некому (личный раннер с office на паузе),
    # её отказ называет причину, а остальные документы встают в очередь.
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz"), make_document("pres")])
    h.given(project, documents=(make_document_definition("tz"), make_document_definition("pres")))
    fit = RunnerFit(tags=frozenset({"office"}), shared=PoolState.absent, personal=PoolState.paused)
    h.dispatcher.refuse_docs["pres"] = NoRunnerAvailableError(frozenset({"office"}), any_runner=True, fit=fit)

    refused: list[NoRunnerAvailableError] = []
    for doc_id in ("tz", "pres"):
        try:
            await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id=doc_id))
        except NoRunnerAvailableError as exc:
            refused.append(exc)

    assert [compile_payload_of(spec).doc_id for spec, _ in h.dispatcher.submitted] == ["tz"]
    ((exc,),) = (refused,)
    assert (exc.code, exc.reason) == ("no_runner_for_tags", RunnerGapReason.personal_paused)
    failed = [call.args[0] for call in h.compile_repo.save.call_args_list if call.args[0].doc_id == "pres"]
    assert [(r.status, r.error_code) for r in failed] == [(CompileStatus.failure, "no_runner_for_tags")]
    assert "на паузе" in (failed[0].error_detail or "")


async def test__trigger_compile__refusal_record_cannot_be_saved__original_refusal_still_raised(tmp_path) -> None:
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h.given(project, documents=(make_document_definition("tz"),))
    h.dispatcher.preflight_error = ImageMissingError("texlive:latest")
    h.compile_repo.save.side_effect = OSError("disk full")

    with pytest.raises(ImageMissingError):
        await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))


async def test__trigger_compile__success__pending_record_and_building_status_before_submit(tmp_path) -> None:
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h.given(project, documents=(make_document_definition("tz"),))

    out = await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))

    record = h.compile_repo.save.call_args.args[0]
    assert (record.id, record.status, record.doc_id, record.log) == (out.compile_id, CompileStatus.pending, "tz", "")
    saved = h.project_repo.save.call_args.args[0]
    assert saved.documents[0].status is DocumentStatus.building
    assert saved.documents[0].last_compile_id == out.compile_id
    hooks = h.dispatcher.submitted[0][1]
    assert isinstance(hooks, CompileJobHooks)


async def test__trigger_compile__build_all__spec_carries_the_batch(tmp_path) -> None:
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h.given(project, documents=(make_document_definition("tz"),))
    batch = uuid.uuid4()

    await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz", batch_id=batch))

    assert h.spec.batch_id == batch


async def test__trigger_compile__english_request__spec_carries_the_interface_language(tmp_path) -> None:
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h.given(project, documents=(make_document_definition("tz"),))
    set_interface_language("en")
    try:
        await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))
    finally:
        set_interface_language("ru")

    assert h.spec.locale is Lang.en


async def test__trigger_compile__check_plan__resolves_rules_and_ignored_ids(tmp_path) -> None:
    doc = replace(make_document("tz"), checks_override=ChecksOverride(disabled=("lt:SOME_RULE",)))
    project = replace(
        make_project(folder=tmp_path, documents=[doc]), checks_override=ChecksOverride(disabled=("proj_rule", "r_off"))
    )
    rules = (
        make_check_rule("r_regex", severity=CheckSeverity.warn),
        make_check_rule("r_off", severity=CheckSeverity.err),
        make_check_rule("r_lt", engine=CheckEngine.external),
    )
    h = Harness(tmp_path)
    h.given(project, documents=(make_document_definition("tz"),), rules=rules)

    await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))

    plan = h.payload.check_plan
    assert {rule.id for rule, _ in plan.rules_with_severity} == {"r_regex", "r_lt"}
    assert plan.ignored_rule_ids == frozenset({"lt:SOME_RULE", "proj_rule", "r_off"})
    assert plan.needs_languagetool is True


async def test__trigger_compile__check_plan__no_external_rule__languagetool_not_needed(tmp_path) -> None:
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h = Harness(tmp_path)
    h.given(project, documents=(make_document_definition("tz"),), rules=(make_check_rule("r_regex"),))

    await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id="tz"))

    assert h.payload.check_plan.needs_languagetool is False


@pytest.mark.parametrize("missing", ["project", "document", "version", "definition"])
async def test__trigger_compile__missing_entity__not_found_before_any_side_effect(tmp_path, missing: str) -> None:
    h = Harness(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("tz")])
    h.given(project, documents=(make_document_definition("tz"),))
    doc_id = "tz"
    if missing == "project":
        h.project_repo.get.return_value = None
    elif missing == "document":
        doc_id = "other"
    elif missing == "version":
        h.template_repo.get_version.return_value = None
    else:
        h.template_repo.get_version.return_value = make_template_version(documents=())

    with pytest.raises(NotFoundError):
        await h.uc.execute(TriggerCompileInput(project_id=project.id, doc_id=doc_id))

    assert h.events == []
