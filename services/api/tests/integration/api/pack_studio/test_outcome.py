"""Эндпоинты результата версии (template-studio-outcome.md, 4.6, срез O2) в локальной Студии над папкой.

Настоящие роутер и DI, настоящие версии репозитория (ВКР `hse-cs-se` 2026.1.2 и курсовой проект `hse-cs-sse` 2026.1.6),
разбор версии в отдельном процессе, как у предпросмотра. Ответы принимают строгие модели контракта и равны ядру
`resolve`. Состояния `head` и `base` над git: `test_outcome_git.py`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.infra.ratelimit.memory import InMemoryRateLimiter
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio import outcome_service
from hse_doc_studio.use_cases.pack_studio.outcome.dictionary import inputs_dictionary
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService

from .conftest import API, Stand
from .outcome_support import (
    COURSEWORK,
    DRAFT_VKR,
    LANGS,
    REAL_VERSIONS,
    VKR,
    edit_manifest,
    folder_with_draft,
    folder_with_real_packs,
    get_inputs,
    parse_inputs,
    parse_outcome,
    post_outcome,
)

TODAY = date(2026, 11, 16)
_BOUNDARY = ("workspace_id", "pack", "template", "version", "state", "elapsed_ms")


@pytest.fixture
async def service(stand: Stand, monkeypatch: pytest.MonkeyPatch) -> PackOutcomeService:
    """Служба результата стенда с зафиксированным днём (ключ кэша и значения по умолчанию зависят от него)."""
    assert stand.container is not None
    found = await stand.container.get(PackOutcomeService)
    monkeypatch.setattr(found, "_today", lambda: TODAY)
    return found


def _core(root: Path, ref: tuple[str, str, str], inputs: dict[str, str] | None = None, **kw: Any) -> dict[str, Any]:
    """Результат ядра на тех же файлах, без HTTP: с него сверяется ответ."""
    version = YamlTemplateRepository(root).get_version(*ref)
    assert version is not None
    example = auto_examples(version)[0]
    return dict(to_json(resolve(version, inputs or {}, example, TODAY, **kw)))


def _without_boundary(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k not in _BOUNDARY and k != "revision"}


# ── ответ и контракт ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", REAL_VERSIONS, ids=lambda r: r[1])
async def test__outcome__real_version__strict_model_and_equal_to_the_core(
    stand: Stand, service: PackOutcomeService, ref: tuple[str, str, str]
) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await post_outcome(stand, ws, ref, {"include": ["checks", "branches"]})

    out = parse_outcome(resp)
    assert (out.workspace_id, out.pack, out.template, out.version, out.state) == (ws, *ref, "work_tree")
    assert out.elapsed_ms >= 0
    assert out.revision.startswith("sha256-")
    body = resp.json()
    expected = _core(stand.root / "packs", ref, include={"checks", "branches"})
    assert _without_boundary(body) == _without_boundary(expected)
    assert out.checks is not None
    assert out.branches is not None
    assert resp.headers["Cache-Control"] == "private, no-cache"


async def test__outcome__without_include__checks_and_branches_are_null(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)

    out = parse_outcome(await post_outcome(stand, ws, COURSEWORK))

    assert out.checks is None
    assert out.branches is None
    assert out.documents


async def test__outcome__request_inputs_are_applied_over_the_defaults(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    inputs = {"kind": "research", "staffing": "team2", "meta.nda": "yes"}

    out = parse_outcome(await post_outcome(stand, ws, VKR, {"inputs": inputs}))

    assert {k: out.inputs[k] for k in inputs} == inputs
    assert out.fingerprint == _core(stand.root / "packs", VKR, inputs)["fingerprint"]
    default = parse_outcome(await post_outcome(stand, ws, VKR))
    assert default.fingerprint != out.fingerprint


@pytest.mark.parametrize("ref", REAL_VERSIONS, ids=lambda r: r[1])
async def test__inputs__real_version__strict_model_and_equal_to_the_dictionary(
    stand: Stand, service: PackOutcomeService, ref: tuple[str, str, str]
) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await get_inputs(stand, ws, ref)

    out = parse_inputs(resp)
    assert (out.workspace_id, out.pack, out.template, out.version, out.state) == (ws, *ref, "work_tree")
    assert out.default_example == "auto:normal"
    assert {e.id for e in out.examples} == {"auto:normal", "auto:long", "auto:empty"}
    version = YamlTemplateRepository(stand.root / "packs").get_version(*ref)
    assert version is not None
    expected = to_json(inputs_dictionary(version, auto_examples(version)[0], TODAY))
    assert resp.json()["inputs"] == expected["inputs"]
    assert out.defaults == expected["defaults"]
    # Умолчания словаря это те же вводные, что считает расчёт без запроса.
    assert parse_outcome(await post_outcome(stand, ws, ref)).inputs == out.defaults


async def test__inputs__state_is_echoed_and_a_wrong_state_is_refused(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)

    ok = await get_inputs(stand, ws, COURSEWORK, "work_tree")
    bad = await get_inputs(stand, ws, COURSEWORK, "tomorrow")

    assert parse_inputs(ok).state == "work_tree"
    assert bad.status_code == 422


# ── ETag, 304 и кэш ──────────────────────────────────────────────────────────


async def test__outcome__etag_is_stable_and_if_none_match_answers_304(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    first = await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}})
    etag = first.headers["ETag"]

    again = await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}})
    not_modified = await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}}, **{"If-None-Match": etag})
    weak = await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}}, **{"If-None-Match": f"W/{etag}"})
    listed = await post_outcome(
        stand, ws, COURSEWORK, {"inputs": {"kind": "project"}}, **{"If-None-Match": f'"other", {etag}'}
    )
    star = await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}}, **{"If-None-Match": "*"})
    stale = await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}}, **{"If-None-Match": '"old"'})

    assert etag.startswith('"')
    assert again.headers["ETag"] == etag
    for resp in (not_modified, weak, listed, star):
        assert resp.status_code == 304
        assert resp.content == b""
        assert resp.headers["ETag"] == etag
        assert resp.headers["Cache-Control"] == "private, no-cache"
    assert stale.status_code == 200
    assert stale.headers["ETag"] == etag


async def test__outcome__etag_depends_on_the_request_and_not_on_the_order_of_inputs(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    a = await post_outcome(stand, ws, VKR, {"inputs": {"kind": "research", "meta.nda": "yes"}})
    b = await post_outcome(stand, ws, VKR, {"inputs": {"meta.nda": "yes", "kind": "research"}})
    other = await post_outcome(stand, ws, VKR, {"inputs": {"kind": "research"}})
    with_include = await post_outcome(
        stand, ws, VKR, {"inputs": {"kind": "research", "meta.nda": "yes"}, "include": ["checks"]}
    )
    inputs_etag = (await get_inputs(stand, ws, VKR)).headers["ETag"]

    assert a.headers["ETag"] == b.headers["ETag"]
    assert len({a.headers["ETag"], other.headers["ETag"], with_include.headers["ETag"], inputs_etag}) == 4
    # Чужой ETag не сходится: у каждого пространства, версии и запроса свой.
    assert (await post_outcome(stand, ws, COURSEWORK, {}, **{"If-None-Match": a.headers["ETag"]})).status_code == 200


async def test__inputs__if_none_match_answers_304(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)
    first = await get_inputs(stand, ws, VKR)

    again = await get_inputs(stand, ws, VKR, **{"If-None-Match": first.headers["ETag"]})

    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["ETag"] == first.headers["ETag"]


async def test__outcome__result_is_cached_by_the_request_and_not_computed_twice(
    stand: Stand, service: PackOutcomeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    calls: list[dict[str, str]] = []
    real = outcome_service.resolve

    def counting(version: Any, inputs: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(dict(inputs))
        return real(version, inputs, *args, **kwargs)

    monkeypatch.setattr(outcome_service, "resolve", counting)

    first = await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}})
    second = await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}})
    await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "research"}})
    await post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": "project"}, "include": ["checks"]})

    assert len(calls) == 3
    assert calls[0] == {"kind": "project"}
    # Из кэша тело то же, кроме времени ответа.
    assert {k: v for k, v in first.json().items() if k != "elapsed_ms"} == {
        k: v for k, v in second.json().items() if k != "elapsed_ms"
    }


async def test__inputs__dictionary_is_cached(
    stand: Stand, service: PackOutcomeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    calls: list[int] = []
    real = outcome_service.inputs_dictionary

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(outcome_service, "inputs_dictionary", counting)

    await get_inputs(stand, ws, COURSEWORK)
    await get_inputs(stand, ws, COURSEWORK)
    await get_inputs(stand, ws, COURSEWORK, "work_tree")

    assert len(calls) == 1


# ── несохранённые правки ─────────────────────────────────────────────────────


async def test__work_tree__unsaved_edit_changes_the_result_the_inputs_and_the_etag(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws, _ = await folder_with_draft(stand)
    before_inputs = parse_inputs(await get_inputs(stand, ws, DRAFT_VKR))
    before = await post_outcome(stand, ws, DRAFT_VKR, {"inputs": {"lang": "en"}})
    assert before.status_code == 200, before.text
    assert [v.value for v in next(i for i in before_inputs.inputs if i.id == "lang").values] == ["ru", "en"]

    await edit_manifest(stand, ws, LANGS, "langs: [ru]")

    after_inputs = parse_inputs(await get_inputs(stand, ws, DRAFT_VKR))
    after = await post_outcome(stand, ws, DRAFT_VKR, {"inputs": {"lang": "en"}})
    stale = await post_outcome(
        stand, ws, DRAFT_VKR, {"inputs": {"lang": "en"}}, **{"If-None-Match": before.headers["ETag"]}
    )
    assert [v.value for v in next(i for i in after_inputs.inputs if i.id == "lang").values] == ["ru"]
    assert after_inputs.revision != before_inputs.revision
    assert after.status_code == 400
    assert (after.json()["code"], after.json()["field"], after.json()["value"]) == ("inputs_invalid", "lang", "en")
    # Прежний ETag больше не подходит: правка сменила `revision`, и 304 нет.
    assert stale.status_code == 400
    # Правка вернулась: возвращается и прежняя ревизия, ответ равен прежнему.
    await edit_manifest(stand, ws, "langs: [ru]", LANGS)
    reverted = await post_outcome(stand, ws, DRAFT_VKR, {"inputs": {"lang": "en"}})
    assert parse_outcome(reverted).revision == before_inputs.revision
    assert reverted.headers["ETag"] == before.headers["ETag"]


async def test__work_tree__edit_of_a_document_file_changes_the_etag_but_not_the_revision(
    stand: Stand, service: PackOutcomeService
) -> None:
    """Правка исходника документа манифесты не меняет: `revision` прежний, а ключ кэша другой (дайджест каталога)."""
    ws, root = await folder_with_draft(stand)
    first = await post_outcome(stand, ws, DRAFT_VKR)
    tex = next((root / "hse-cs-se/templates/vkr/versions/2026.1.9/files").rglob("*.tex"))

    tex.write_text(tex.read_text(encoding="utf-8") + "\n% edited\n", encoding="utf-8")

    second = await post_outcome(stand, ws, DRAFT_VKR)
    assert parse_outcome(second).revision == parse_outcome(first).revision
    assert second.headers["ETag"] != first.headers["ETag"]


# ── ошибки ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("inputs", "field", "value"),
    [
        ({"kind": "poetry"}, "kind", "poetry"),
        ({"no_such_input": "x"}, "no_such_input", "x"),
        ({"meta.nda": "maybe"}, "meta.nda", "maybe"),
        ({"answer.no.field": "yes"}, "answer.no.field", "yes"),
        ({"kind": "p" * 129}, "kind", "p" * 129),
    ],
)
async def test__outcome__bad_inputs__inputs_invalid_with_field_value_and_reason(
    stand: Stand, service: PackOutcomeService, inputs: dict[str, str], field: str, value: str
) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await post_outcome(stand, ws, VKR, {"inputs": inputs})

    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "inputs_invalid"
    assert (body["field"], body["value"]) == (field, value)
    assert body["reason"]


async def test__outcome__unknown_example__inputs_invalid_on_the_example(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)

    bad = await post_outcome(stand, ws, VKR, {"example": "nope"})
    good = await post_outcome(stand, ws, VKR, {"example": "auto:long"})

    assert bad.status_code == 400
    assert (bad.json()["code"], bad.json()["field"], bad.json()["value"]) == ("inputs_invalid", "example", "nope")
    assert parse_outcome(good).example == "auto:long"


async def test__outcome__scenario_is_not_found_until_scenarios_exist(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await post_outcome(stand, ws, VKR, {"scenario": "company-supervisor"})

    assert resp.status_code == 404
    assert resp.json()["code"] == "scenario_not_found"


async def test__outcome__too_many_or_unknown_fields__validation_error(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)

    many = await post_outcome(stand, ws, VKR, {"inputs": {f"k{i}": "v" for i in range(65)}})
    extra = await post_outcome(stand, ws, VKR, {"surprise": 1})
    state = await post_outcome(stand, ws, VKR, {"state": "tomorrow"})

    assert many.status_code == extra.status_code == state.status_code == 422


async def test__outcome__missing_version_and_workspace(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)

    version = await post_outcome(stand, ws, ("hse-cs-se", "vkr", "2099.1.1"))
    template = await post_outcome(stand, ws, ("hse-cs-se", "nope", "2026.1.2"))
    inputs = await get_inputs(stand, ws, ("hse-cs-se", "vkr", "2099.1.1"))
    nowhere = await post_outcome(stand, "6f1c1c8e-1b7a-4d51-9a43-0a5b2f3c4d10", VKR)
    traversal = await stand.client.post(f"{API}/workspaces/{ws}/versions/hse-cs-se/vkr/..%2F..%2Fx/outcome", json={})

    assert (version.status_code, version.json()["code"]) == (404, "version_not_found")
    assert (inputs.status_code, inputs.json()["code"]) == (404, "version_not_found")
    assert template.status_code == 404
    assert (nowhere.status_code, nowhere.json()["code"]) == (404, "workspace_not_found")
    assert traversal.status_code in {400, 404}
    assert "path_not_allowed" in traversal.text or traversal.status_code == 404


async def test__outcome__folder_has_no_head_and_base__diff_base_unavailable(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)

    for state in ("head", "base"):
        resp = await post_outcome(stand, ws, VKR, {"state": state})
        listed = await get_inputs(stand, ws, VKR, state)
        for r in (resp, listed):
            assert r.status_code == 409, r.text
            assert r.json()["code"] == "diff_base_unavailable"
            assert r.json()["reason"] == "no_git"


async def test__outcome__unreadable_version__version_unreadable_with_the_reason(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws, root = await folder_with_draft(stand)
    manifest = root / "hse-cs-se/templates/vkr/versions/2026.1.9/version.yaml"
    manifest.write_text("id: [unclosed\n", encoding="utf-8")

    resp = await post_outcome(stand, ws, DRAFT_VKR)

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "version_unreadable"


# ── права ────────────────────────────────────────────────────────────────────


async def test__outcome__section_turned_off__refused_before_anything_is_read(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    off = await stand.client.put(f"{API}/section", json={"enabled": False})
    assert off.status_code == 200, off.text

    post = await post_outcome(stand, ws, VKR)
    get = await get_inputs(stand, ws, VKR)

    for resp in (post, get):
        assert resp.status_code == 404
        assert resp.json()["code"] == "pack_studio_disabled"


# ── большой набор вводных ────────────────────────────────────────────────────


async def test__outcome__all_inputs_of_the_dictionary_at_once__answered_and_echoed(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    dictionary = parse_inputs(await get_inputs(stand, ws, VKR))
    # Каждая вводная своим непредусмотренным по умолчанию значением, насколько оно есть: самый большой запрос версии.
    inputs = {i.id: next((v.value for v in i.values if v.value != i.default), i.default) for i in dictionary.inputs}
    assert len(inputs) >= 10
    assert len(inputs) <= 64

    first = await post_outcome(stand, ws, VKR, {"inputs": inputs})
    reordered = await post_outcome(stand, ws, VKR, {"inputs": dict(reversed(list(inputs.items())))})

    out = parse_outcome(first)
    assert out.inputs == inputs
    assert first.headers["ETag"] == reordered.headers["ETag"]
    assert out.fingerprint == _core(stand.root / "packs", VKR, inputs)["fingerprint"]


# ── предел времени и перегрузка ──────────────────────────────────────────────


@pytest.fixture
def slow_resolve(monkeypatch: pytest.MonkeyPatch) -> float:
    """Расчёт, который долго держит поток (как залипший или очень тяжёлый)."""
    delay = 0.6
    real = outcome_service.resolve

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(delay)
        return real(*args, **kwargs)

    monkeypatch.setattr(outcome_service, "resolve", slow)
    return delay


async def test__outcome__calculation_over_the_time_limit__503_outcome_busy_with_retry_after(
    stand: Stand, service: PackOutcomeService, slow_resolve: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    await get_inputs(stand, ws, COURSEWORK)  # разбор версии в отдельном процессе не входит в предел расчёта
    monkeypatch.setattr(service, "_limits", replace(service._limits, timeout_s=0.1))
    started = time.perf_counter()

    resp = await post_outcome(stand, ws, COURSEWORK)

    assert time.perf_counter() - started < slow_resolve
    assert resp.status_code == 503, resp.text
    assert resp.json()["code"] == "outcome_busy"
    assert resp.json()["reason"] == "timeout"
    assert resp.headers["Retry-After"] == str(outcome_service.RETRY_AFTER_S)
    # Неудачный расчёт в кэш не попал: после того как поток освободился, тот же запрос проходит.
    monkeypatch.setattr(service, "_limits", replace(service._limits, timeout_s=5.0))
    await asyncio.sleep(slow_resolve)
    assert (await post_outcome(stand, ws, COURSEWORK)).status_code == 200


async def test__outcome__more_requests_than_the_process_can_hold__overloaded_answers_at_once(
    stand: Stand, service: PackOutcomeService, slow_resolve: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    monkeypatch.setattr(service, "_limits", replace(service._limits, max_pending=2, timeout_s=10.0))
    await post_outcome(stand, ws, COURSEWORK)  # прогрев разбора версии: дальше время тратит только расчёт

    answers = await asyncio.gather(
        *(
            post_outcome(stand, ws, COURSEWORK, {"inputs": {"kind": kind}})
            for kind in ("project", "research", "project")
        )
    )

    codes = sorted(r.status_code for r in answers)
    # Два места заняты, третьему отказ; одинаковые запросы не считаются дважды только из кэша, а он ещё пуст.
    assert codes.count(503) >= 1
    refused = next(r for r in answers if r.status_code == 503)
    assert refused.json() == {
        "detail": refused.json()["detail"],
        "code": "outcome_busy",
        "reason": "overloaded",
        "retry_after_s": outcome_service.RETRY_AFTER_S,
    }
    assert refused.headers["Retry-After"] == str(outcome_service.RETRY_AFTER_S)
    assert 200 in codes


async def test__outcome__default_limits_follow_the_design(service: PackOutcomeService) -> None:
    assert service._limits.timeout_s == 5.0
    assert service._limits.cache_entries == 256


# ── частота ──────────────────────────────────────────────────────────────────


async def test__outcome__rate_limit__21st_request_in_a_second_is_refused_with_retry_after(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    app = stand.client._transport.app  # type: ignore[attr-defined]
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.rate_limit_scale = 1.0
    await post_outcome(stand, ws, COURSEWORK)  # разбор версии не должен съесть секунду окна

    start = time.perf_counter()
    answers = [await post_outcome(stand, ws, COURSEWORK) for _ in range(25)]

    if time.perf_counter() - start < 1.0:
        refused = [r for r in answers if r.status_code == 429]
        assert refused
        assert refused[0].headers["Retry-After"] == "1"
        assert refused[0].json()["code"] == "rate_limited"
    assert answers[0].status_code == 200
