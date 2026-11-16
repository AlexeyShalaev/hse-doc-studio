"""Эндпоинт «Почему?» (template-studio-outcome.md, 4.6, срез O5) в локальной Студии над папкой и над git.

Настоящие роутер и DI, настоящие версии репозитория (ВКР `hse-cs-se` 2026.1.2 и курсовой проект `hse-cs-sse` 2026.1.6),
разбор версии в отдельном процессе. Ответы принимают строгие модели контракта, равны эталону и пересчёту ядром.
Права под PG: `test_pack_studio_server_pg.py`."""

from __future__ import annotations

import asyncio
import functools
import json
import time
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeExplainResponse
from hse_doc_studio.core.pack_studio.outcome.explain import explain_element
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef, Outcome
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio import outcome_service
from hse_doc_studio.use_cases.pack_studio.outcome.explain import EXPLAIN_INCLUDE, neighbors_of
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService
from httpx import Response

from .conftest import API, Stand
from .outcome_support import (
    COURSEWORK,
    DRAFT_VKR,
    FIXTURES,
    REAL_VERSIONS,
    VKR,
    edit_manifest,
    folder_with_draft,
    folder_with_real_packs,
    outcome_url,
    post_outcome,
)
from .test_outcome_git import _ready

TODAY = date(2026, 11, 16)
_NDA_ITEM = {"section": "points", "id": "final/nda"}
_NDA_ITEM_BEFORE = "        - doc_id: nda\n          signatures: []\n"
_NDA_ITEM_AFTER = "        - doc_id: nda\n          signatures: []\n          supported_kinds: [research]\n"


@pytest.fixture
async def service(stand: Stand, monkeypatch: pytest.MonkeyPatch) -> PackOutcomeService:
    """Служба результата стенда с зафиксированным днём (ключ кэша и значения по умолчанию зависят от него)."""
    assert stand.container is not None
    found = await stand.container.get(PackOutcomeService)
    monkeypatch.setattr(found, "_today", lambda: TODAY)
    return found


async def post_explain(
    stand: Stand,
    ws: str,
    ref: tuple[str, str, str],
    element: Mapping[str, str],
    body: Mapping[str, Any] | None = None,
    **headers: str,
) -> Response:
    return await stand.client.post(
        outcome_url(ws, ref, "/explain"), json={**(body or {}), "element": dict(element)}, headers=headers
    )


def parse_explain(resp: Response) -> PackOutcomeExplainResponse:
    """Ответ принимает строгая модель контракта: лишние и недостающие поля отвергаются."""
    assert resp.status_code == 200, resp.text
    return PackOutcomeExplainResponse.model_validate(resp.json())


@functools.cache
def _calculated(root: str, ref: tuple[str, str, str], inputs: tuple[tuple[str, str], ...]) -> tuple[Outcome, Any]:
    version = YamlTemplateRepository(Path(root)).get_version(*ref)
    assert version is not None
    example = auto_examples(version)[0]
    outcome = resolve(version, dict(inputs), example, TODAY, include=EXPLAIN_INCLUDE)
    return outcome, neighbors_of(version, outcome, example, TODAY)


def _core(
    root: Path, ref: tuple[str, str, str], element: Mapping[str, str], inputs: dict[str, str] | None = None
) -> dict[str, Any]:
    """Объяснение ядром на тех же файлах, без HTTP: с него сверяется ответ."""
    outcome, neighbors = _calculated(str(root), ref, tuple(sorted((inputs or {}).items())))
    found = explain_element(outcome, ElementRef(element["section"], element["id"]), neighbors)  # type: ignore[arg-type]
    assert found is not None
    return dict(to_json(found))


def _changes(out: PackOutcomeExplainResponse) -> dict[tuple[str, str], str]:
    return {(c.input, c.value): c.result for c in out.counterfactuals}


# ── ответ и контракт ─────────────────────────────────────────────────────────


async def test__explain__fixture_request__answer_equals_the_reference(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    request = json.loads((FIXTURES / "PackOutcomeExplainRequest" / "operator_manual.json").read_text("utf-8"))
    expected = json.loads((FIXTURES / "PackOutcomeExplain" / "operator_manual.json").read_text("utf-8"))

    resp = await stand.client.post(outcome_url(ws, VKR, "/explain"), json=request)

    parse_explain(resp)
    assert resp.json() == expected
    assert resp.headers["Cache-Control"] == "private, no-cache"
    assert resp.headers["ETag"]


@pytest.mark.parametrize("ref", REAL_VERSIONS, ids=lambda r: r[1])
async def test__explain__every_element_of_the_outcome__strict_model_and_equal_to_the_core(
    stand: Stand, service: PackOutcomeService, ref: tuple[str, str, str]
) -> None:
    ws = await folder_with_real_packs(stand)
    out = (await post_outcome(stand, ws, ref, {"include": ["checks"]})).json()
    elements = (
        [("documents", d["id"]) for d in out["documents"]]
        + [("meta", f["id"]) for f in out["meta"]]
        + [("participants", p["persona"]) for p in out["participants"]]
        + [("points", f"{p['id']}/{i['doc_id']}") for p in out["points"] for i in p["items"]]
        + [("route", p["id"]) for p in out["points"]]
        + [("route", f"{p['id']}/{r['doc_id']}/{r['slot_id']}") for p in out["points"] for r in p["route"]["skipped"]]
        + [("checks", c["id"]) for c in out["checks"]]
    )
    assert len(elements) > 50

    for section, element_id in elements:
        element = {"section": section, "id": element_id}
        resp = await post_explain(stand, ws, ref, element)

        parse_explain(resp)
        assert resp.json() == _core(stand.root / "packs", ref, element), element


async def test__explain__chain_of_a_document_equals_its_why_in_the_outcome(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    inputs = {"meta.nda": "no", "meta.manuals": "Только оператора"}
    outcome = (await post_outcome(stand, ws, VKR, {"inputs": inputs})).json()
    trace = {t["id"]: t for t in outcome["trace"]}

    for doc in outcome["documents"]:
        resp = await post_explain(stand, ws, VKR, {"section": "documents", "id": doc["id"]}, {"inputs": inputs})

        out = parse_explain(resp)
        assert out.state == doc["state"]
        assert [t.id for t in out.chain] == doc["why"]
        assert [t.model_dump() for t in out.chain] == [trace[i] for i in doc["why"]]


async def test__explain__included_and_excluded_document_nda_item_slot_and_field(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    manuals = {"inputs": {"meta.manuals": "Только программиста", "meta.nda": "no"}}

    included = parse_explain(
        await post_explain(stand, ws, VKR, {"section": "documents", "id": "programmer_manual"}, manuals)
    )
    excluded = parse_explain(
        await post_explain(stand, ws, VKR, {"section": "documents", "id": "operator_manual"}, manuals)
    )
    nda_off = parse_explain(await post_explain(stand, ws, VKR, _NDA_ITEM, manuals))
    nda_on = parse_explain(await post_explain(stand, ws, VKR, _NDA_ITEM, {"inputs": {"meta.nda": "yes"}}))
    slot = parse_explain(
        await post_explain(
            stand,
            ws,
            COURSEWORK,
            {"section": "route", "id": "topic-approval/topic_application/co_supervisor"},
            {"inputs": {"co_supervisor": "no"}},
        )
    )
    field = parse_explain(
        await post_explain(
            stand,
            ws,
            VKR,
            {"section": "forms", "id": "ai_declaration/tools"},
            {"inputs": {"answer.ai_declaration.used_ai": "no"}},
        )
    )

    assert (included.state, excluded.state) == ("active", "inactive")
    assert {t.status for t in excluded.chain} == {"held", "not_held"}
    assert _changes(excluded)[("meta.manuals", "Программиста и оператора")] == "active"
    assert (nda_off.state, nda_on.state) == ("absent", "present")
    assert _changes(nda_off) == {("meta.nda", "yes"): "present"}
    assert slot.state == "absent"
    assert [t.status for t in slot.chain] == ["not_held"]
    assert _changes(slot) == {("co_supervisor", "yes"): "present"}
    assert field.state == "absent"
    assert _changes(field) == {("answer.ai_declaration.used_ai", "yes"): "present"}


async def test__explain__what_if_equals_the_real_recalculation(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)
    inputs = {"meta.manuals": "Только программиста"}
    explained = parse_explain(
        await post_explain(stand, ws, VKR, {"section": "documents", "id": "operator_manual"}, {"inputs": inputs})
    )

    assert explained.counterfactuals
    for change in explained.counterfactuals:
        after = (await post_outcome(stand, ws, VKR, {"inputs": {**inputs, change.input: change.value}})).json()
        doc = next(d for d in after["documents"] if d["id"] == "operator_manual")
        assert doc["state"] == change.result != explained.state


async def test__explain__inputs_example_and_unknown_inputs(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)
    element = {"section": "documents", "id": "operator_manual"}

    bad = await post_explain(stand, ws, VKR, element, {"inputs": {"kind": "no such kind"}})
    bad_example = await post_explain(stand, ws, VKR, element, {"example": "no-such-example"})
    scenario = await post_explain(stand, ws, VKR, element, {"scenario": "s1"})

    assert (bad.status_code, bad.json()["code"], bad.json()["field"]) == (400, "inputs_invalid", "kind")
    assert (bad_example.status_code, bad_example.json()["field"]) == (400, "example")
    assert (scenario.status_code, scenario.json()["code"]) == (404, "scenario_not_found")


# ── неизвестный элемент и разбор тела ────────────────────────────────────────


@pytest.mark.parametrize(
    "element",
    [
        {"section": "documents", "id": "no_such_document"},
        {"section": "points", "id": "final/no_such_item"},
        {"section": "route", "id": "final/step/99"},
        {"section": "participants", "id": "nobody"},
        {"section": "checks", "id": "no-such-rule"},
    ],
    ids=lambda e: e["id"],
)
async def test__explain__unknown_element__404_with_section_and_id(
    stand: Stand, service: PackOutcomeService, element: dict[str, str]
) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await post_explain(stand, ws, VKR, element)

    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["code"] == "outcome_element_not_found"
    assert (body["section"], body["id"]) == (element["section"], element["id"])
    assert body["detail"]


async def test__explain__element_of_the_other_version_is_unknown(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await post_explain(stand, ws, COURSEWORK, {"section": "documents", "id": "operator_manual"})

    assert resp.json()["code"] == "outcome_element_not_found"


async def test__explain__malformed_body__validation_error(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)
    url = outcome_url(ws, VKR, "/explain")

    no_element = await stand.client.post(url, json={})
    bad_section = await stand.client.post(url, json={"element": {"section": "nope", "id": "x"}})
    empty_id = await stand.client.post(url, json={"element": {"section": "documents", "id": ""}})
    extra = await stand.client.post(url, json={"element": {"section": "documents", "id": "nda"}, "include": ["checks"]})
    too_many = await stand.client.post(
        url,
        json={"element": {"section": "documents", "id": "nda"}, "inputs": {f"i{n}": "x" for n in range(65)}},
    )

    assert {r.status_code for r in (no_element, bad_section, empty_id, extra, too_many)} == {422}


async def test__explain__missing_version_and_workspace(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)
    element = {"section": "documents", "id": "nda"}

    no_version = await post_explain(stand, ws, ("hse-cs-se", "vkr", "2099.1.1"), element)
    no_workspace = await post_explain(stand, "00000000-0000-0000-0000-000000000000", VKR, element)

    assert (no_version.status_code, no_version.json()["code"]) == (404, "version_not_found")
    assert (no_workspace.status_code, no_workspace.json()["code"]) == (404, "workspace_not_found")


# ── права ────────────────────────────────────────────────────────────────────


async def test__explain__section_turned_off__refused_before_anything_is_read(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    off = await stand.client.put("/api/v1/pack-studio/section", json={"enabled": False})
    assert off.status_code == 200, off.text

    resp = await post_explain(stand, ws, VKR, {"section": "documents", "id": "nda"})

    assert resp.status_code == 404
    assert resp.json()["code"] == "pack_studio_disabled"


# ── ETag и кэш ───────────────────────────────────────────────────────────────


async def test__explain__etag_is_stable_and_if_none_match_answers_304_without_computing(
    stand: Stand, service: PackOutcomeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    element = {"section": "documents", "id": "operator_manual"}
    first = await post_explain(stand, ws, VKR, element)
    etag = first.headers["ETag"]
    monkeypatch.setattr(outcome_service, "resolve", _forbidden)
    monkeypatch.setattr(outcome_service, "neighbors_of", _forbidden)

    again = await post_explain(stand, ws, VKR, element, **{"If-None-Match": etag})
    weak = await post_explain(stand, ws, VKR, element, **{"If-None-Match": f"W/{etag}"})
    star = await post_explain(stand, ws, VKR, element, **{"If-None-Match": "*"})
    stale = await post_explain(stand, ws, VKR, element, **{"If-None-Match": '"stale"'})

    assert first.status_code == 200
    for resp in (again, weak, star):
        assert resp.status_code == 304
        assert resp.headers["ETag"] == etag
        assert resp.content == b""
    assert stale.status_code == 200  # ответ из кэша, ничего не считалось
    assert stale.json() == first.json()


def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("ответ должен прийти без расчёта")


async def test__explain__etag_depends_on_element_inputs_and_state_and_not_on_the_order_of_inputs(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    element = {"section": "documents", "id": "operator_manual"}
    inputs = {"kind": "project", "staffing": "solo"}

    base = await post_explain(stand, ws, VKR, element, {"inputs": inputs})
    reordered = await post_explain(stand, ws, VKR, element, {"inputs": dict(reversed(list(inputs.items())))})
    other_element = await post_explain(
        stand, ws, VKR, {"section": "documents", "id": "programmer_manual"}, {"inputs": inputs}
    )
    other_inputs = await post_explain(stand, ws, VKR, element, {"inputs": {"kind": "research"}})
    outcome = await post_outcome(stand, ws, VKR, {"inputs": inputs})

    assert base.headers["ETag"] == reordered.headers["ETag"]
    assert len({r.headers["ETag"] for r in (base, other_element, other_inputs, outcome)}) == 4


async def test__explain__result_is_cached_and_neighbors_are_shared_between_elements(
    stand: Stand, service: PackOutcomeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    calls = {"resolve": 0, "neighbors": 0}
    real_resolve, real_neighbors = outcome_service.resolve, outcome_service.neighbors_of

    def counting_resolve(*args: Any, **kwargs: Any) -> Any:
        calls["resolve"] += 1
        return real_resolve(*args, **kwargs)

    def counting_neighbors(*args: Any, **kwargs: Any) -> Any:
        calls["neighbors"] += 1
        return real_neighbors(*args, **kwargs)

    monkeypatch.setattr(outcome_service, "resolve", counting_resolve)
    monkeypatch.setattr(outcome_service, "neighbors_of", counting_neighbors)
    await post_explain(stand, ws, VKR, {"section": "documents", "id": "operator_manual"})  # прогрев разбора версии
    assert calls == {"resolve": 1, "neighbors": 1}

    repeat = await post_explain(stand, ws, VKR, {"section": "documents", "id": "operator_manual"})
    another = await post_explain(stand, ws, VKR, {"section": "documents", "id": "programmer_manual"})
    other_inputs = await post_explain(
        stand, ws, VKR, {"section": "documents", "id": "operator_manual"}, {"inputs": {"kind": "research"}}
    )

    assert (repeat.status_code, another.status_code, other_inputs.status_code) == (200, 200, 200)
    # Повтор из кэша ответа; другой элемент тех же вводных берёт готовые результат и соседей; новые вводные считаются.
    assert calls == {"resolve": 2, "neighbors": 2}


async def test__explain__work_tree__unsaved_edit_changes_the_answer_and_the_etag(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws, _ = await folder_with_draft(stand)
    body = {"inputs": {"meta.nda": "yes"}}
    before = await post_explain(stand, ws, DRAFT_VKR, _NDA_ITEM, body)

    await edit_manifest(stand, ws, _NDA_ITEM_BEFORE, _NDA_ITEM_AFTER)
    after = await post_explain(stand, ws, DRAFT_VKR, _NDA_ITEM, body)

    assert parse_explain(before).state == "present"
    assert parse_explain(before).chain == []
    changed = parse_explain(after)
    assert changed.state == "absent"
    assert [(t.kind, t.status) for t in changed.chain] == [("item_kinds", "not_held")]
    assert changed.chain[0].rule.pointer is not None
    assert changed.chain[0].rule.pointer.endswith("/supported_kinds")
    assert _changes(changed) == {("kind", "research"): "present"}
    assert before.headers["ETag"] != after.headers["ETag"]


# ── предел времени и перегрузка ──────────────────────────────────────────────


async def test__explain__calculation_over_the_time_limit__503_outcome_busy_with_retry_after(
    stand: Stand, service: PackOutcomeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    element = {"section": "documents", "id": "operator_manual"}
    await post_explain(stand, ws, COURSEWORK, element | {"id": "report"})  # разбор версии не входит в предел расчёта
    delay = 0.6
    real = outcome_service.resolve

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(delay)
        return real(*args, **kwargs)

    monkeypatch.setattr(outcome_service, "resolve", slow)
    monkeypatch.setattr(service, "_limits", replace(service._limits, timeout_s=0.1))
    started = time.perf_counter()

    resp = await post_explain(
        stand, ws, COURSEWORK, {"section": "documents", "id": "report"}, {"inputs": {"kind": "research"}}
    )

    assert time.perf_counter() - started < delay
    assert resp.status_code == 503, resp.text
    assert resp.json()["code"] == "outcome_busy"
    assert resp.json()["reason"] == "timeout"
    assert resp.headers["Retry-After"] == str(outcome_service.RETRY_AFTER_S)
    # Неудачный расчёт в кэш не попал: после того как поток освободился, тот же запрос проходит.
    monkeypatch.setattr(service, "_limits", replace(service._limits, timeout_s=5.0))
    await asyncio.sleep(delay)
    again = await post_explain(
        stand, ws, COURSEWORK, {"section": "documents", "id": "report"}, {"inputs": {"kind": "research"}}
    )
    assert again.status_code == 200


async def test__explain__neighbors_over_the_time_limit__503_and_the_next_try_reuses_the_outcome(
    stand: Stand, service: PackOutcomeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    element = {"section": "documents", "id": "operator_manual"}
    await post_explain(stand, ws, VKR, element)  # прогрев разбора версии
    delay = 0.6
    real = outcome_service.neighbors_of

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(delay)
        return real(*args, **kwargs)

    monkeypatch.setattr(outcome_service, "neighbors_of", slow)
    monkeypatch.setattr(service, "_limits", replace(service._limits, timeout_s=0.1))

    resp = await post_explain(stand, ws, VKR, element, {"inputs": {"kind": "research"}})

    assert (resp.status_code, resp.json()["code"], resp.json()["reason"]) == (503, "outcome_busy", "timeout")
    monkeypatch.setattr(service, "_limits", replace(service._limits, timeout_s=5.0))
    await asyncio.sleep(delay)
    assert (await post_explain(stand, ws, VKR, element, {"inputs": {"kind": "research"}})).status_code == 200


async def test__explain__more_requests_than_the_process_can_hold__overloaded_answers_at_once(
    stand: Stand, service: PackOutcomeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    element = {"section": "documents", "id": "report"}
    await post_explain(stand, ws, COURSEWORK, element)  # прогрев разбора версии
    real = outcome_service.resolve

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.5)
        return real(*args, **kwargs)

    monkeypatch.setattr(outcome_service, "resolve", slow)
    monkeypatch.setattr(service, "_limits", replace(service._limits, max_pending=2, timeout_s=10.0))

    answers = await asyncio.gather(
        *(
            post_explain(stand, ws, COURSEWORK, element, {"inputs": {"kind": kind}})
            for kind in ("project", "research", "project")
        )
    )

    refused = [r for r in answers if r.status_code == 503]
    assert refused
    assert refused[0].json()["code"] == "outcome_busy"
    assert refused[0].json()["reason"] == "overloaded"
    assert refused[0].headers["Retry-After"] == str(outcome_service.RETRY_AFTER_S)
    assert any(r.status_code == 200 for r in answers)


# ── три состояния версии ─────────────────────────────────────────────────────


async def test__explain__folder_has_no_head_and_base__diff_base_unavailable(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)

    for state in ("head", "base"):
        resp = await post_explain(stand, ws, VKR, _NDA_ITEM, {"state": state})

        assert (resp.status_code, resp.json()["code"], resp.json()["reason"]) == (
            409,
            "diff_base_unavailable",
            "no_git",
        )


async def test__explain__three_states__unsaved_edit_is_seen_in_work_tree_only(stand: Stand) -> None:
    _, ws = await _ready(stand)
    body = {"inputs": {"meta.nda": "yes"}}
    await edit_manifest(stand, ws, _NDA_ITEM_BEFORE, _NDA_ITEM_AFTER)

    answers = {
        state: await post_explain(stand, ws, DRAFT_VKR, _NDA_ITEM, {**body, "state": state})
        for state in ("work_tree", "head", "base")
    }

    parsed = {state: parse_explain(resp) for state, resp in answers.items()}
    assert {state: out.state for state, out in parsed.items()} == {
        "work_tree": "absent",
        "head": "present",
        "base": "present",
    }
    assert [t.kind for t in parsed["work_tree"].chain] == ["item_kinds"]
    assert parsed["head"].chain == parsed["base"].chain == []
    assert len({resp.headers["ETag"] for resp in answers.values()}) == 3
    # `head` и `base` читаются из коммита, и повтор не считается заново.
    again = await post_explain(
        stand, ws, DRAFT_VKR, _NDA_ITEM, {**body, "state": "head"}, **{"If-None-Match": answers["head"].headers["ETag"]}
    )
    assert again.status_code == 304


async def test__explain__commit_moves_head_but_not_base(stand: Stand) -> None:
    _, ws = await _ready(stand)
    body = {"inputs": {"meta.nda": "yes"}}
    await edit_manifest(stand, ws, _NDA_ITEM_BEFORE, _NDA_ITEM_AFTER)
    before = await post_explain(stand, ws, DRAFT_VKR, _NDA_ITEM, {**body, "state": "head"})

    committed = await stand.client.post(f"{API}/workspaces/{ws}/git/commit", json={})
    assert committed.status_code == 200, committed.text
    head = await post_explain(stand, ws, DRAFT_VKR, _NDA_ITEM, {**body, "state": "head"})
    base = await post_explain(stand, ws, DRAFT_VKR, _NDA_ITEM, {**body, "state": "base"})

    assert parse_explain(before).state == "present"
    assert parse_explain(head).state == "absent"
    assert parse_explain(base).state == "present"
    assert head.headers["ETag"] != before.headers["ETag"]


async def test__explain__new_version_has_no_head_and_base(stand: Stand) -> None:
    _, ws = await _ready(stand)
    new = ("hse-cs-se", "vkr", "2026.1.10")
    created = await stand.client.put(
        stand.file_url(ws, "hse-cs-se/templates/vkr/versions/2026.1.10/version.yaml"),
        content=b'id: "2026.1.10"\nstatus: beta\nlangs: [ru]\n',
    )
    assert created.status_code == 200, created.text

    work = await post_explain(stand, ws, new, {"section": "participants", "id": "author"})
    head = await post_explain(stand, ws, new, {"section": "participants", "id": "author"}, {"state": "head"})

    assert work.status_code == 200, work.text
    assert (head.status_code, head.json()["reason"]) == (409, "new_version")
