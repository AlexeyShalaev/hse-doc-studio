"""Правила слияния файлов состояния: документы собраны настоящими сериализаторами и репозиториями."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import DetachedFormat, DetachedOrigin, DetachedVerdict, SignMode
from hse_doc_studio.core.git_sync.entities import SyncWarningCode
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.merge.choices import (
    FieldChoice,
    FieldDecision,
    FieldsResolution,
    FileChoice,
    FileChoiceResolution,
)
from hse_doc_studio.core.git_sync.merge.entities import ConflictType, ContentKind, MergeAction
from hse_doc_studio.core.git_sync.merge.jsonmerge import InvalidFieldChoiceError, canonical_dumps
from hse_doc_studio.core.git_sync.merge.planner import MergeInput, plan_merge, resolve_plan
from hse_doc_studio.core.git_sync.merge.rules import StateFileMerge, rules_for
from hse_doc_studio.core.git_sync.protocols import MergeDecision, MergeMeta
from hse_doc_studio.core.template_update.entities import (
    FileWrite,
    FileWriteKind,
    TemplateTrackingState,
    TemplateUpdateRecord,
)
from hse_doc_studio.core.value_objects import (
    Author,
    DetachedSignature,
    FormState,
    FrozenPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
from hse_doc_studio.infra.persistence.forms import JsonFormStateRepository
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_form_state,
    deserialize_project,
    deserialize_signatures_state,
)
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine
from hse_doc_studio.infra.template_update.state import JsonTemplateTrackingRepository

from tests.factories import make_document, make_project

_PROJECT = ".hse-studio/project.json"
_SIGNATURES = ".hse-studio/signatures.json"
_TEMPLATE = ".hse-studio/template.json"
_FORM = ".hse-studio/forms/ai_declaration.json"
_T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

_STRATEGY = StateFileMerge(
    {
        "project": lambda value: deserialize_project(value, Path("/project")),
        "signatures": deserialize_signatures_state,
        "form": deserialize_form_state,
    }
)

Json = dict[str, Any]


def _enc(value: Any) -> bytes:
    return canonical_dumps(value).encode()


def _load(raw: bytes | None) -> Json:
    assert raw is not None
    return json.loads(raw)


def _merge(path: str, base: Json, ours: Json, theirs: Json, meta: MergeMeta | None = None) -> MergeDecision:
    return _STRATEGY.merge(path, _enc(base), _enc(ours), _enc(theirs), meta or MergeMeta())


def _edited(doc: Json, change: Callable[[Json], None]) -> Json:
    result = copy.deepcopy(doc)
    change(result)
    return result


def _doc(folder: Path, relative: str) -> Json:
    return json.loads((folder / relative).read_text(encoding="utf-8"))


# --- настоящие документы -----------------------------------------------------------------------


def _project() -> Project:
    project = make_project(documents=[make_document("a"), make_document("b")])
    authors = [Author(name="Анна", slug="anna", meta={"udc": "1"}), Author(name="Пётр", slug="petr")]
    return replace(project, id=UUID(int=1), created_at=_T0, updated_at=_T0, authors=authors)


@pytest.fixture
def project_json(tmp_path: Path) -> Json:
    JsonProjectRepository().save(replace(_project(), folder=tmp_path))
    return _doc(tmp_path, _PROJECT)


@pytest.fixture
def signatures_json(tmp_path: Path) -> Json:
    state = SignaturesState(
        slots={
            "author--anna": SignatureSlot("signatures/anna.png", 100, 50, signing_identity_id="id-1"),
            "author--petr": SignatureSlot("signatures/petr.png", 80, 40, sign_mode=SignMode.detached),
        },
        placements={"a": {"author--anna": SignaturePlacement(True, 1, 10.0, 20.0, 40.0)}},
        frozen={"a": FrozenPdf("frozen/a.pdf", "f1", "s1", 10, "2026-10-01T10:00:00+00:00")},
        detached={
            "a": {
                "author--anna": DetachedSignature(
                    "detached/a.sig",
                    DetachedFormat.cms,
                    DetachedOrigin.uploaded,
                    "f1",
                    DetachedVerdict.valid,
                    "Анна",
                    "x",
                    "t",
                )
            }
        },
    )
    JsonSignatureRepository().save_state(tmp_path, state)
    return _doc(tmp_path, _SIGNATURES)


@pytest.fixture
def form_json(tmp_path: Path) -> Json:
    state = FormState(1, False, {"tool": "gpt", "uses": ["draft"], "note": {"a": 1}})
    JsonFormStateRepository().save_state(tmp_path, "ai_declaration", state)
    return _doc(tmp_path, _FORM)


def _template_json(tmp_path: Path) -> Json:
    record = TemplateUpdateRecord("u1", "2026.1", "2026.2", "2026-10-02T10:00:00+00:00", "p1", commit="c1")
    JsonTemplateTrackingRepository().save(tmp_path, TemplateTrackingState(frozenset({"a.tex"}), (record,)))
    return _doc(tmp_path, _TEMPLATE)


@pytest.fixture
def template_json(tmp_path: Path) -> Json:
    return _template_json(tmp_path)


def test__canonical_dumps__is_what_the_repositories_write(
    tmp_path: Path, project_json: Json, signatures_json: Json, form_json: Json, template_json: Json
) -> None:
    for relative in (_PROJECT, _SIGNATURES, _FORM, _TEMPLATE):
        text = (tmp_path / relative).read_text(encoding="utf-8")
        assert canonical_dumps(json.loads(text)) == text


@pytest.mark.parametrize(
    ("path", "name"),
    [
        (_PROJECT, "project"),
        (_SIGNATURES, "signatures"),
        (_TEMPLATE, "template"),
        (_FORM, "form"),
        (".hse-studio/other.json", "state"),
        (".hse-studio/deep/x.json", "state"),
    ],
)
def test__rules_for__picks_rules_by_path(path: str, name: str) -> None:
    rules = rules_for(path)

    assert rules is not None
    assert rules.name == name


@pytest.mark.parametrize("path", ["data.json", "refs/.hse-studio/x.json", ".hse-studio/x.png", "a.tex"])
def test__rules_for__not_a_state_file__is_none(path: str) -> None:
    assert rules_for(path) is None


# --- project.json ------------------------------------------------------------------------------


def _compile(doc: Json, doc_id: str, compile_id: str, minutes: int) -> Json:
    def change(data: Json) -> None:
        for item in data["documents"]:
            if item["id"] == doc_id:
                item["last_compile_id"] = compile_id
        data["updated_at"] = (_T0 + timedelta(minutes=minutes)).isoformat()

    return _edited(doc, change)


def test__project__two_compiles_on_two_machines__merge_without_conflicts(project_json: Json) -> None:
    ours = _compile(project_json, "a", str(UUID(int=11)), 5)
    theirs = _compile(project_json, "b", str(UUID(int=12)), 9)

    decision = _merge(_PROJECT, project_json, ours, theirs)

    assert not decision.conflict
    merged = _load(decision.content)
    assert merged["updated_at"] == theirs["updated_at"]
    # Номер сборки чужой машины здесь ничего не значит: свои остаются своими.
    assert {d["id"]: d["last_compile_id"] for d in merged["documents"]} == {"a": str(UUID(int=11)), "b": None}
    assert decision.fields == ()


def test__project__two_compiles_of_the_same_document__merge_without_conflicts(project_json: Json) -> None:
    ours = _compile(project_json, "a", str(UUID(int=11)), 5)
    theirs = _compile(project_json, "a", str(UUID(int=12)), 9)

    decision = _merge(_PROJECT, project_json, ours, theirs)

    assert not decision.conflict
    assert _load(decision.content)["documents"][0]["last_compile_id"] == str(UUID(int=11))


def test__project__merge_is_the_same_on_both_machines_except_local_fields(project_json: Json) -> None:
    ours = _compile(project_json, "a", str(UUID(int=11)), 5)
    theirs = _edited(project_json, lambda d: d["authors"].append({"name": "Иван", "slug": "ivan", "managed": True}))

    forward = _load(_merge(_PROJECT, project_json, ours, theirs).content)
    backward = _load(_merge(_PROJECT, project_json, theirs, ours).content)

    assert forward["authors"] == backward["authors"]
    assert forward["updated_at"] == backward["updated_at"] == ours["updated_at"]


def test__project__pinned_archived_and_vcs_settings_stay_mine(project_json: Json) -> None:
    def mine(data: Json) -> None:
        data["pinned"] = True
        data["meta"]["vcs"] = {"auto": True}

    def theirs_change(data: Json) -> None:
        data["archived"] = True
        data["meta"]["vcs"] = {"auto": False}
        data["name"] = "Новое имя"

    decision = _merge(_PROJECT, project_json, _edited(project_json, mine), _edited(project_json, theirs_change))

    merged = _load(decision.content)
    assert (merged["pinned"], merged["archived"], merged["meta"]["vcs"]) == (True, False, {"auto": True})
    assert merged["name"] == "Новое имя"
    assert not decision.conflict


def test__project__authors_and_documents_added_on_both_sides__are_united_by_key(project_json: Json) -> None:
    def add(slug: str) -> Callable[[Json], None]:
        def change(data: Json) -> None:
            data["authors"].append({"name": slug, "slug": slug, "managed": True})
            data["documents"].append(copy.deepcopy(data["documents"][0]) | {"id": f"doc-{slug}"})

        return change

    decision = _merge(_PROJECT, project_json, _edited(project_json, add("zed")), _edited(project_json, add("ivan")))

    merged = _load(decision.content)
    assert [a["slug"] for a in merged["authors"]] == ["anna", "petr", "ivan", "zed"]
    assert [d["id"] for d in merged["documents"]] == ["a", "b", "doc-ivan", "doc-zed"]
    assert not decision.conflict


def test__project__document_status_changed_differently__is_a_conflict_on_that_field(project_json: Json) -> None:
    def status(value: str) -> Callable[[Json], None]:
        return lambda data: data["documents"][0].update(status=value)

    decision = _merge(
        _PROJECT, project_json, _edited(project_json, status("ready")), _edited(project_json, status("submitted"))
    )

    assert decision.conflict
    assert decision.conflict_type == ConflictType.fields.value
    assert [(f.pointer, f.ours, f.theirs) for f in decision.fields] == [("/documents/@a/status", "ready", "submitted")]
    assert _load(decision.content)["documents"][0]["status"] == "ready"


def test__project__lock_takes_the_record_with_the_higher_template_version(project_json: Json) -> None:
    def lock(version: str, digest: str) -> Callable[[Json], None]:
        return lambda data: data["lock"].update(version=version, digest=digest)

    decision = _merge(
        _PROJECT,
        _edited(project_json, lock("2026.1", "d0")),
        _edited(project_json, lock("2026.3", "d3")),
        _edited(project_json, lock("2026.2.1", "d2")),
    )

    assert not decision.conflict
    assert _load(decision.content)["lock"]["version"] == "2026.3"
    assert _load(decision.content)["lock"]["digest"] == "d3"


def test__project__lock_with_another_template__is_a_conflict(project_json: Json) -> None:
    def template(name: str) -> Callable[[Json], None]:
        return lambda data: data["lock"].update(template_id=name, version="2026.9")

    decision = _merge(
        _PROJECT, project_json, _edited(project_json, template("x")), _edited(project_json, template("y"))
    )

    assert [f.pointer for f in decision.fields] == ["/lock"]


def test__project__schema_takes_the_maximum_and_created_at_the_minimum(project_json: Json) -> None:
    def newer(data: Json) -> None:
        data["schema"].update(version=3, read_compat=2, write_compat=3, written_by="0.10.0")
        data["created_at"] = (_T0 - timedelta(days=1)).isoformat()

    def other(data: Json) -> None:
        data["schema"].update(version=2, read_compat=1, write_compat=2, written_by="0.9.5")
        data["created_at"] = (_T0 + timedelta(days=1)).isoformat()

    decision = _merge(_PROJECT, project_json, _edited(project_json, other), _edited(project_json, newer))

    merged = _load(decision.content)
    assert merged["schema"] == {"version": 3, "read_compat": 2, "write_compat": 3, "written_by": "0.10.0"}
    assert merged["created_at"] == (_T0 - timedelta(days=1)).isoformat()
    assert not decision.conflict


def test__project__another_project_id__is_a_conflict_even_if_only_one_side_changed(project_json: Json) -> None:
    decision = _merge(
        _PROJECT, project_json, project_json, _edited(project_json, lambda d: d.update(id=str(UUID(int=2))))
    )

    assert [f.pointer for f in decision.fields] == ["/id"]


def test__project__checks_override_lists_are_sets(project_json: Json) -> None:
    def disable(rule: str) -> Callable[[Json], None]:
        return lambda data: data["documents"][0]["checks_override"]["disabled"].append(rule)

    decision = _merge(
        _PROJECT, project_json, _edited(project_json, disable("r1")), _edited(project_json, disable("r2"))
    )

    assert _load(decision.content)["documents"][0]["checks_override"]["disabled"] == ["r1", "r2"]


def test__project__deleted_document_that_i_only_compiled__is_deleted(project_json: Json) -> None:
    ours = _compile(project_json, "b", str(UUID(int=11)), 3)
    theirs = _edited(project_json, lambda d: d["documents"].pop(1))

    decision = _merge(_PROJECT, project_json, ours, theirs)

    assert not decision.conflict
    assert [d["id"] for d in _load(decision.content)["documents"]] == ["a"]


def test__project__fields_of_a_newer_studio__pass_through_untouched(project_json: Json) -> None:
    def newer(data: Json) -> None:
        data["future"] = {"x": [1, 2]}
        data["documents"][0]["future_doc"] = "k"
        data["authors"][0]["future_author"] = 7

    def mine(data: Json) -> None:
        data["mine_only"] = True

    decision = _merge(_PROJECT, project_json, _edited(project_json, mine), _edited(project_json, newer))

    merged = _load(decision.content)
    assert merged["future"] == {"x": [1, 2]}
    assert merged["mine_only"] is True
    assert merged["documents"][0]["future_doc"] == "k"
    assert merged["authors"][0]["future_author"] == 7


def test__project__result_that_does_not_deserialize__is_a_forced_invalid_result_conflict(project_json: Json) -> None:
    strategy = StateFileMerge({"project": lambda value: value["no-such-key"]})
    ours = _edited(project_json, lambda d: d.update(name="О"))
    theirs = _edited(project_json, lambda d: d.update(kind="research"))

    decision = strategy.merge(_PROJECT, _enc(project_json), _enc(ours), _enc(theirs), MergeMeta())

    assert (decision.conflict, decision.conflict_type) == (True, ConflictType.invalid_result.value)
    assert decision.content == _enc(ours)
    assert decision.fields == ()


def test__project__resolution_that_breaks_the_document__is_rejected(project_json: Json) -> None:
    def valid_unless_theirs_status(value: Json) -> None:
        if value["documents"][0]["status"] == "submitted":
            raise ValueError

    strategy = StateFileMerge({"project": valid_unless_theirs_status})
    ours = _edited(project_json, lambda d: d["documents"][0].update(status="ready"))
    theirs = _edited(project_json, lambda d: d["documents"][0].update(status="submitted"))
    args = (_PROJECT, _enc(project_json), _enc(ours), _enc(theirs), MergeMeta())

    assert strategy.merge(*args).conflict_type == ConflictType.fields.value
    with pytest.raises(InvalidFieldChoiceError):
        strategy.resolve(*args, {"/documents/@a/status": FieldChoice.theirs})
    assert not strategy.resolve(*args, {"/documents/@a/status": FieldChoice.mine}).conflict


def test__project__unparsable_side__is_merged_as_text() -> None:
    decision = _STRATEGY.merge(_PROJECT, b"{}", b"{not json", b"{}", MergeMeta())

    assert decision.as_text


def test__strategy__a_path_without_rules_or_a_deleted_side__is_merged_as_text() -> None:
    assert _STRATEGY.merge("data.json", b"{}", b"{}", b"{}", MergeMeta()).as_text
    assert _STRATEGY.merge(_PROJECT, b"{}", None, b"{}", MergeMeta()).as_text


def test__strategy__result_equal_to_one_side__is_returned_in_that_sides_bytes(project_json: Json) -> None:
    ours = _edited(project_json, lambda d: d.update(name="Новое"))
    raw_ours = json.dumps(ours, indent=4).encode()

    decision = _STRATEGY.merge(
        _PROJECT,
        _enc(project_json),
        raw_ours,
        _enc(_edited(project_json, lambda d: d.update(archived=True))),
        MergeMeta(),
    )

    # `archived` чужой остаётся чужим, итог совпал с моим файлом: форматирование не меняется зря.
    assert decision.content == raw_ours


def test__strategy__no_common_base__merges_against_an_empty_document() -> None:
    decision = _STRATEGY.merge(".hse-studio/x.json", None, _enc({"a": 1}), _enc({"b": 2}), MergeMeta())

    assert _load(decision.content) == {"a": 1, "b": 2}


def test__strategy__generic_state_file__merges_by_keys_and_keeps_lists_whole() -> None:
    path = ".hse-studio/new-feature.json"
    base, ours, theirs = {"a": 1, "l": [1]}, {"a": 2, "l": [1]}, {"a": 1, "l": [1, 2], "z": True}

    decision = _STRATEGY.merge(path, _enc(base), _enc(ours), _enc(theirs), MergeMeta())

    assert _load(decision.content) == {"a": 2, "l": [1, 2], "z": True}


# --- signatures.json ---------------------------------------------------------------------------


def test__signatures__slots_and_placements_of_different_people__are_united(signatures_json: Json) -> None:
    def mine(data: Json) -> None:
        data["placements"]["a"]["author--petr"] = {
            "enabled": True,
            "page": 2,
            "x_mm": 1.0,
            "y_mm": 2.0,
            "width_mm": 3.0,
        }

    def theirs_change(data: Json) -> None:
        data["slots"]["author--ivan"] = {
            "png_path": "signatures/ivan.png",
            "natural_width_px": 5,
            "natural_height_px": 5,
        }

    decision = _merge(
        _SIGNATURES, signatures_json, _edited(signatures_json, mine), _edited(signatures_json, theirs_change)
    )

    merged = _load(decision.content)
    assert not decision.conflict
    assert set(merged["slots"]) == {"author--anna", "author--petr", "author--ivan"}
    assert "author--petr" in merged["placements"]["a"]


def test__signatures__signing_identity_and_mode_never_come_from_the_other_machine(signatures_json: Json) -> None:
    def theirs_change(data: Json) -> None:
        data["slots"]["author--anna"].update(signing_identity_id="their-id", sign_mode="image_crypto")
        data["slots"]["author--new"] = {
            "png_path": None,
            "natural_width_px": None,
            "natural_height_px": None,
            "signing_identity_id": "their-id",
            "sign_mode": "image_crypto",
            "sign_reason": "",
            "signer": None,
        }

    decision = _merge(_SIGNATURES, signatures_json, signatures_json, _edited(signatures_json, theirs_change))

    slots = _load(decision.content)["slots"]
    assert (slots["author--anna"]["signing_identity_id"], slots["author--anna"]["sign_mode"]) == ("id-1", "image")
    assert (slots["author--new"]["signing_identity_id"], slots["author--new"]["sign_mode"]) == (None, "image")
    assert not decision.conflict


def test__signatures__picture_and_its_size_follow_the_newer_side_together(signatures_json: Json) -> None:
    def picture(path: str, size: int) -> Callable[[Json], None]:
        return lambda data: data["slots"]["author--anna"].update(png_path=path, natural_width_px=size)

    ours = _edited(signatures_json, picture("signatures/mine.png", 111))
    theirs = _edited(signatures_json, picture("signatures/theirs.png", 222))
    older, newer = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)

    theirs_newer = _merge(_SIGNATURES, signatures_json, ours, theirs, MergeMeta(older, newer, "a", "b"))
    ours_newer = _merge(_SIGNATURES, signatures_json, ours, theirs, MergeMeta(newer, older, "a", "b"))

    won = _load(theirs_newer.content)["slots"]["author--anna"]
    assert (won["png_path"], won["natural_width_px"]) == ("signatures/theirs.png", 222)
    lost = _load(ours_newer.content)["slots"]["author--anna"]
    assert (lost["png_path"], lost["natural_width_px"]) == ("signatures/mine.png", 111)
    assert not theirs_newer.conflict
    assert theirs_newer.auto[0].pointer == "/slots/author--anna/png_path"


def test__signatures__placement_changed_by_both__is_one_conflict_for_the_record(signatures_json: Json) -> None:
    def move(x: float) -> Callable[[Json], None]:
        return lambda data: data["placements"]["a"]["author--anna"].update(x_mm=x)

    decision = _merge(
        _SIGNATURES, signatures_json, _edited(signatures_json, move(1.0)), _edited(signatures_json, move(2.0))
    )

    assert [f.pointer for f in decision.fields] == ["/placements/a/author--anna"]


def _refrozen(sha: str, signed: bool) -> Callable[[Json], None]:
    def change(data: Json) -> None:
        data["frozen"]["a"].update(sha256=sha)
        if not signed:
            data["detached"] = {}

    return change


def test__signatures__frozen_pdf_and_signatures_changed_by_both__is_a_signature_group_conflict(
    signatures_json: Json,
) -> None:
    ours = _edited(signatures_json, _refrozen("f2", signed=False))
    theirs = _edited(signatures_json, _refrozen("f3", signed=True))

    decision = _merge(_SIGNATURES, signatures_json, ours, theirs)

    assert decision.conflict
    assert decision.conflict_type == ConflictType.signature_group.value
    (group,) = decision.fields
    assert group.pointer == "/signature_groups/a"
    assert group.ours["detached"] is None
    assert group.theirs["frozen"]["sha256"] == "f3"
    chosen = _STRATEGY.resolve(
        _SIGNATURES, _enc(signatures_json), _enc(ours), _enc(theirs), MergeMeta(), {group.pointer: FieldChoice.theirs}
    )
    assert _load(chosen.content)["frozen"]["a"]["sha256"] == "f3"
    assert "a" in _load(chosen.content)["detached"]


def test__signatures__the_group_comes_from_one_side_never_mixed(signatures_json: Json) -> None:
    ours = _edited(signatures_json, _refrozen("f2", signed=False))

    decision = _merge(_SIGNATURES, signatures_json, ours, signatures_json)

    merged = _load(decision.content)
    assert (merged["frozen"]["a"]["sha256"], merged["detached"]) == ("f2", {})


def test__signatures__a_signature_over_another_pdf__gives_a_stale_warning_without_changing_data(
    signatures_json: Json,
) -> None:
    ours = _edited(signatures_json, lambda d: d["frozen"]["a"].update(sha256="other"))

    decision = _merge(_SIGNATURES, signatures_json, ours, signatures_json)

    assert not decision.conflict
    assert [(w.code, w.paths) for w in decision.warnings] == [(SyncWarningCode.signatures_stale, ("frozen/a.pdf",))]
    assert _load(decision.content)["frozen"]["a"]["sha256"] == "other"


def test__signatures__consistent_signatures__give_no_warning(signatures_json: Json) -> None:
    ours = _edited(signatures_json, lambda d: d["slots"]["author--anna"].update(sign_reason="why"))

    assert _merge(_SIGNATURES, signatures_json, ours, signatures_json).warnings == ()


# --- forms/*.json ------------------------------------------------------------------------------


def test__form__different_answers__are_merged_and_the_checkmark_is_dropped(form_json: Json) -> None:
    ours = _edited(form_json, lambda d: d.update(completed=True))
    theirs = _edited(form_json, lambda d: d["answers"].update(tool="claude"))

    decision = _merge(_FORM, form_json, ours, theirs)

    merged = _load(decision.content)
    assert merged["answers"]["tool"] == "claude"
    assert merged["completed"] is False
    assert not decision.conflict


def test__form__completed_with_the_answers_that_were_signed_off__stays_completed(form_json: Json) -> None:
    ours = _edited(form_json, lambda d: d.update(completed=True))

    decision = _merge(_FORM, form_json, ours, form_json)

    assert _load(decision.content)["completed"] is True


def test__form__both_edited_after_one_signed_off__is_not_completed(form_json: Json) -> None:
    def signed_off(data: Json) -> None:
        data["completed"] = True
        data["answers"]["tool"] = "a"

    ours = _edited(form_json, signed_off)
    theirs = _edited(form_json, lambda d: d["answers"].update(note={"a": 2}))

    assert _load(_merge(_FORM, form_json, ours, theirs).content)["completed"] is False
    assert _load(_merge(_FORM, form_json, theirs, ours).content)["completed"] is False


def test__form__completed_by_both__keeps_the_and_of_both(form_json: Json) -> None:
    done = _edited(form_json, lambda d: d.update(completed=True))
    reopened = _edited(form_json, lambda d: d.update(completed=False))

    assert _load(_merge(_FORM, done, done, reopened).content)["completed"] is False


def test__form__list_answer_changed_by_both__is_a_conflict_with_union(form_json: Json) -> None:
    ours = _edited(form_json, lambda d: d["answers"]["uses"].append("code"))
    theirs = _edited(form_json, lambda d: d["answers"]["uses"].append("text"))

    decision = _merge(_FORM, form_json, ours, theirs)

    (field,) = decision.fields
    assert (field.pointer, field.allowed) == (
        "/answers/uses",
        (FieldChoice.mine, FieldChoice.theirs, FieldChoice.union),
    )
    resolved = _STRATEGY.resolve(
        _FORM, _enc(form_json), _enc(ours), _enc(theirs), MergeMeta(), {"/answers/uses": FieldChoice.union}
    )
    assert _load(resolved.content)["answers"]["uses"] == ["draft", "code", "text"]


def test__form__schema_version_takes_the_maximum(form_json: Json) -> None:
    decision = _merge(
        _FORM,
        form_json,
        _edited(form_json, lambda d: d.update(schema_version=2)),
        _edited(form_json, lambda d: d.update(schema_version=3)),
    )

    assert _load(decision.content)["schema_version"] == 3


# --- template.json -----------------------------------------------------------------------------


def _record(record_id: str, at: str, **extra: Any) -> Json:
    return {
        "id": record_id,
        "from_version": "2026.1",
        "to_version": "2026.2",
        "at": at,
        "pre_commit": "p",
        "commit": None,
        "markers": [],
        "reverted": False,
        "reverts": None,
    } | extra


def test__template__history_is_united_by_id_and_sorted_by_time(template_json: Json) -> None:
    ours = _edited(template_json, lambda d: d["history"].append(_record("u3", "2026-10-05T00:00:00+00:00")))
    theirs = _edited(template_json, lambda d: d["history"].append(_record("u2", "2026-10-03T00:00:00+00:00")))

    forward = _merge(_TEMPLATE, template_json, ours, theirs)
    backward = _merge(_TEMPLATE, template_json, theirs, ours)

    assert [r["id"] for r in _load(forward.content)["history"]] == ["u1", "u2", "u3"]
    assert forward.content == backward.content
    assert not forward.conflict


def test__template__reverted_is_or_and_the_commit_that_exists_wins(template_json: Json) -> None:
    base = _edited(template_json, lambda d: d["history"][0].update(commit=None))
    ours = _edited(base, lambda d: d["history"][0].update(reverted=True))
    theirs = _edited(base, lambda d: d["history"][0].update(commit="c9", reverted=False))
    # Чужая правка `reverted` совпадает с базой, поэтому берётся моя, а коммит приходит из чужой.
    merged = _load(_merge(_TEMPLATE, base, ours, theirs).content)["history"][0]
    assert (merged["reverted"], merged["commit"]) == (True, "c9")

    both = _edited(base, lambda d: d["history"][0].update(reverted=True, commit="c1"))
    other = _edited(base, lambda d: d["history"][0].update(reverted=False, commit="c1"))
    assert not _merge(_TEMPLATE, base, both, other).conflict


def test__template__ignored_files_are_a_sorted_set(template_json: Json) -> None:
    ours = _edited(template_json, lambda d: d["ignored"].append("z.tex"))
    theirs = _edited(template_json, lambda d: d.update(ignored=["b.tex"]))

    decision = _merge(_TEMPLATE, template_json, ours, theirs)

    assert _load(decision.content)["ignored"] == ["b.tex", "z.tex"]


# --- в составе планировщика --------------------------------------------------------------------


def _plan(
    engine: GitMergeFileEngine, files: tuple[Json, Json, Json], path: str = _PROJECT, meta: MergeMeta | None = None
):  # noqa: ANN202
    base, ours, theirs = (_enc(item) for item in files)
    inp = MergeInput({path: base}, {path: ours}, {path: theirs}, meta={path: meta or MergeMeta()})
    return plan_merge(inp, engine, _STRATEGY)


def test__planner__two_compiles__are_a_single_clean_merged_file(engine: GitMergeFileEngine, project_json: Json) -> None:
    ours = _compile(project_json, "a", str(UUID(int=11)), 5)
    theirs = _compile(project_json, "b", str(UUID(int=12)), 9)

    plan = _plan(engine, (project_json, ours, theirs))

    assert plan.is_clean
    (op,) = plan.ops
    assert (op.kind, op.action) == (ContentKind.json, MergeAction.merged)
    assert "/updated_at" in [a.pointer for a in op.auto]
    assert resolve_plan(plan, {}) == [FileWrite(_PROJECT, FileWriteKind.write, op.merged)]


def test__planner__field_conflict__is_resolved_by_field_through_the_strategy(
    engine: GitMergeFileEngine, project_json: Json
) -> None:
    ours = _edited(project_json, lambda d: d["documents"][0].update(status="ready", chosen_variant="v1"))
    theirs = _edited(project_json, lambda d: d["documents"][0].update(status="submitted", chosen_variant="v2"))
    plan = _plan(engine, (project_json, ours, theirs))

    (op,) = plan.conflicts
    assert op.conflict_type is ConflictType.fields
    assert sorted(f.pointer for f in op.fields) == ["/documents/@a/chosen_variant", "/documents/@a/status"]

    decisions = {
        "/documents/@a/status": FieldDecision(FieldChoice.theirs),
        "/documents/@a/chosen_variant": FieldDecision(FieldChoice.mine),
    }
    (write,) = resolve_plan(plan, {_PROJECT: FieldsResolution(decisions)}, _STRATEGY)
    document = _load(write.content)["documents"][0]
    assert (document["status"], document["chosen_variant"]) == ("submitted", "v1")


def test__planner__partial_field_decisions__are_unresolved(engine: GitMergeFileEngine, project_json: Json) -> None:
    ours = _edited(project_json, lambda d: d["documents"][0].update(status="ready", chosen_variant="v1"))
    theirs = _edited(project_json, lambda d: d["documents"][0].update(status="submitted", chosen_variant="v2"))
    plan = _plan(engine, (project_json, ours, theirs))
    partial = FieldsResolution({"/documents/@a/status": FieldDecision(FieldChoice.mine)})

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {_PROJECT: partial}, _STRATEGY)

    assert error.value.code is GitErrorCode.unresolved_conflicts
    assert error.value.ctx == {"paths": [_PROJECT]}


@pytest.mark.parametrize(
    "decisions",
    [{"/nope": FieldDecision(FieldChoice.mine)}, {"/documents/@a/status": FieldDecision(FieldChoice.union)}],
)
def test__planner__unknown_pointer_or_a_choice_the_field_does_not_allow__is_invalid(
    engine: GitMergeFileEngine, project_json: Json, decisions: dict[str, FieldDecision]
) -> None:
    ours = _edited(project_json, lambda d: d["documents"][0].update(status="ready"))
    theirs = _edited(project_json, lambda d: d["documents"][0].update(status="submitted"))
    plan = _plan(engine, (project_json, ours, theirs))

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {_PROJECT: FieldsResolution(decisions)}, _STRATEGY)

    assert error.value.code is GitErrorCode.invalid_resolution


def test__planner__file_level_choice__still_works_for_a_field_conflict(
    engine: GitMergeFileEngine, project_json: Json
) -> None:
    ours = _edited(project_json, lambda d: d["documents"][0].update(status="ready"))
    theirs = _edited(project_json, lambda d: d["documents"][0].update(status="submitted"))
    plan = _plan(engine, (project_json, ours, theirs))

    assert resolve_plan(plan, {_PROJECT: FileChoiceResolution(FileChoice.mine)}) == []
    (write,) = resolve_plan(plan, {_PROJECT: FileChoiceResolution(FileChoice.theirs)})
    assert write.content == _enc(theirs)


def test__planner__signature_group_conflict__has_its_own_type(
    engine: GitMergeFileEngine, signatures_json: Json
) -> None:
    ours = _edited(signatures_json, _refrozen("f2", signed=False))
    theirs = _edited(signatures_json, _refrozen("f3", signed=True))

    plan = _plan(engine, (signatures_json, ours, theirs), _SIGNATURES)

    (op,) = plan.conflicts
    assert op.conflict_type is ConflictType.signature_group
    (write,) = resolve_plan(
        plan, {_SIGNATURES: FieldsResolution({"/signature_groups/a": FieldDecision(FieldChoice.theirs)})}, _STRATEGY
    )
    assert _load(write.content)["frozen"]["a"]["sha256"] == "f3"


def test__planner__stale_signature_warning__reaches_the_plan(engine: GitMergeFileEngine, signatures_json: Json) -> None:
    ours = _edited(signatures_json, lambda d: d["frozen"]["a"].update(sha256="other"))
    theirs = _edited(signatures_json, lambda d: d["slots"]["author--anna"].update(sign_reason="why"))

    plan = _plan(engine, (signatures_json, ours, theirs), _SIGNATURES)

    assert [w.code for w in plan.warnings] == [SyncWarningCode.signatures_stale]


def test__planner__invalid_result__is_decided_by_file(engine: GitMergeFileEngine, project_json: Json) -> None:
    def broken(value: Json) -> None:
        raise ValueError(value)

    strategy = StateFileMerge({"project": broken})
    ours = _edited(project_json, lambda d: d.update(name="О"))
    theirs = _edited(project_json, lambda d: d.update(lang="en"))
    base, mine, other = (_enc(item) for item in (project_json, ours, theirs))
    plan = plan_merge(MergeInput({_PROJECT: base}, {_PROJECT: mine}, {_PROJECT: other}), engine, strategy)

    (op,) = plan.conflicts
    assert op.conflict_type is ConflictType.invalid_result
    assert resolve_plan(plan, {_PROJECT: FileChoiceResolution(FileChoice.mine)}, strategy) == []
    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {_PROJECT: FieldsResolution({"/name": FieldDecision(FieldChoice.mine)})}, strategy)
    assert error.value.code is GitErrorCode.invalid_resolution


def test__planner__broken_state_json__falls_back_to_text_merge(engine: GitMergeFileEngine) -> None:
    path = ".hse-studio/forms/x.json"
    inp = MergeInput({path: b"{\n}\n"}, {path: b"{\n broken\n}\n"}, {path: b"{\n other\n}\n"})

    plan = plan_merge(inp, engine, _STRATEGY)

    (op,) = plan.ops
    assert op.kind is ContentKind.text
    assert op.conflict_type is ConflictType.content
