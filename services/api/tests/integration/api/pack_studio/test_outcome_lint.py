"""Линтер результата по HTTP (template-studio-outcome.md, разделы 4.6 и 6, срез O8) в локальной Студии над папкой.

Настоящие роутер и DI, настоящие версии репозитория (ВКР `hse-cs-se` 2026.1.2, курсовой проект `hse-cs-sse` 2026.1.6)
и черновик ВКР `2026.1.9`, который можно править. Ответ принимает строгая модель контракта. Проверяются находки на
реальных паках и на правках, ETag и 304, покрытие сценариями, правила по файлам (Jinja) по кнопке, находки в общем
списке `/lint`, права и частота."""

from __future__ import annotations

import time
from typing import Any

from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeLintResponse
from hse_doc_studio.infra.ratelimit.memory import InMemoryRateLimiter
from httpx import Response

from .conftest import API, Stand
from .outcome_support import (
    COURSEWORK,
    DRAFT_VKR,
    LANGS,
    VKR,
    edit_manifest,
    folder_with_draft,
    folder_with_real_packs,
    outcome_url,
)
from .scenario_support import COURSEWORK_TEMPLATE, put_scenario, scenario_body

_VISIBLE_IF = 'equals: "yes"'


async def _lint(stand: Stand, ws: str, ref: tuple[str, str, str], **params: Any) -> Response:
    return await stand.client.get(outcome_url(ws, ref, "/lint"), params=params or None)


def _parse(resp: Response) -> PackOutcomeLintResponse:
    assert resp.status_code == 200, resp.text
    return PackOutcomeLintResponse.model_validate(resp.json())


def _rules(body: PackOutcomeLintResponse) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in body.findings:
        counts[item.rule_id] = counts.get(item.rule_id, 0) + 1
    return counts


async def test__vkr__known_findings_coverage_and_the_strict_model(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await _lint(stand, ws, VKR)

    body = _parse(resp)
    assert (body.pack, body.template, body.version, body.state) == (*VKR, "work_tree")
    assert (body.errors, body.warnings) == (0, 12)
    assert _rules(body) == {"slot-never-routed": 1, "route-step-without-person": 5, "translation-missing": 6}
    assert [f.severity for f in body.findings] == ["warning"] * 12
    assert all(f.hint and f.file == "version.yaml" and f.pointer and f.line for f in body.findings)
    assert body.coverage.rows_total == 864
    assert body.coverage.scenarios == 0
    assert body.coverage.rules_covered == 0
    assert body.coverage.rules_uncovered == body.coverage.rules_total > 0
    assert 0 < len(body.coverage.uncovered_rows) <= 10
    assert body.jinja == "not_run"
    assert not body.atlas_skipped
    assert resp.headers["Cache-Control"] == "private, no-cache"
    assert resp.headers["ETag"].startswith('"')


async def test__coursework__scenarios_of_the_template_give_the_coverage(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    # В копии паков сценариев ещё нет: кладём один через запись сценария, как это делает экран.
    put = await put_scenario(
        stand,
        ws,
        COURSEWORK_TEMPLATE,
        "company",
        scenario_body("Компания", {"supervisor": "company"}, versions=["2026.1.*"]),
    )
    assert put.status_code == 200, put.text

    body = _parse(await _lint(stand, ws, COURSEWORK))

    assert body.coverage.scenarios == 1
    assert body.coverage.rows_total == 12
    assert body.coverage.rows_touched == 1
    assert 0 < body.coverage.percent < 100
    assert body.coverage.rules_covered + body.coverage.rules_half + body.coverage.rules_uncovered == (
        body.coverage.rules_total
    )
    partial = [r for r in body.coverage.rules if r.witness]
    assert partial
    assert all(set(r.witness) == {"supervisor", "co_supervisor", "academic_supervisor"} for r in partial)


async def test__etag__if_none_match_answers_304_and_jinja_has_its_own_etag(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    first = await _lint(stand, ws, COURSEWORK)
    etag = first.headers["ETag"]

    same = await stand.client.get(outcome_url(ws, COURSEWORK, "/lint"), headers={"If-None-Match": etag})
    jinja = await _lint(stand, ws, COURSEWORK, jinja="true")

    assert same.status_code == 304
    assert same.headers["ETag"] == etag
    assert same.content == b""
    assert jinja.headers["ETag"] != etag
    assert _parse(jinja).jinja == "ran"


async def test__scenario_edit__changes_the_etag_and_the_coverage(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    before = await _lint(stand, ws, COURSEWORK)

    await put_scenario(stand, ws, COURSEWORK_TEMPLATE, "none", scenario_body("Нет", {"supervisor": "none"}))
    after = await stand.client.get(
        outcome_url(ws, COURSEWORK, "/lint"), headers={"If-None-Match": before.headers["ETag"]}
    )

    assert after.status_code == 200
    assert after.headers["ETag"] != before.headers["ETag"]
    assert _parse(after).coverage.scenarios == 1


async def test__draft__an_unsaved_edit_adds_a_finding_and_changes_the_etag(stand: Stand) -> None:
    ws, _ = await folder_with_draft(stand)
    clean = await _lint(stand, ws, DRAFT_VKR)
    assert "visible-if-value-not-in-options" not in _rules(_parse(clean))

    await edit_manifest(stand, ws, _VISIBLE_IF, 'equals: "maybe"')

    broken = await _lint(stand, ws, DRAFT_VKR)
    body = _parse(broken)
    assert broken.headers["ETag"] != clean.headers["ETag"]
    assert body.errors >= 1
    assert body.findings[0].severity == "error"
    item = next(f for f in body.findings if f.rule_id == "visible-if-value-not-in-options")
    assert item.pointer
    assert item.pointer.endswith("/visible_if/equals")
    assert item.line
    # Поле с недостижимым условием в атласе скрыто всегда (обязательное было бы ошибкой `required-hidden`).
    assert {"required-hidden", "field-never-visible"} & set(_rules(body))


async def test__draft__a_langs_edit_is_seen_by_the_translation_rule(stand: Stand) -> None:
    ws, _ = await folder_with_draft(stand)

    await edit_manifest(stand, ws, LANGS, "langs: [ru]")

    assert "translation-missing" not in _rules(_parse(await _lint(stand, ws, DRAFT_VKR)))


async def test__jinja__a_broken_template_is_an_error_only_on_request(stand: Stand) -> None:
    ws, root = await folder_with_draft(stand)
    tex = root / "hse-cs-se/templates/vkr/versions/2026.1.9/files/thesis/thesis.ru.tex"
    tex.write_text(
        tex.read_text(encoding="utf-8") + "\n{{ 1 // (project.supervisor.name | length) }}\n", encoding="utf-8"
    )

    plain = _parse(await _lint(stand, ws, DRAFT_VKR))
    asked = _parse(await _lint(stand, ws, DRAFT_VKR, jinja="true"))

    assert "jinja-fail-open" not in _rules(plain)
    assert plain.jinja == "not_run"
    assert asked.jinja == "ran"
    assert asked.errors == 1
    item = next(f for f in asked.findings if f.rule_id == "jinja-fail-open")
    assert item.severity == "error"
    assert item.file == "files/thesis/thesis.ru.tex"
    assert item.line is not None
    assert item.hint


async def test__jinja__on_real_packs_the_button_finds_nothing(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    body = _parse(await _lint(stand, ws, COURSEWORK, jinja="true"))

    assert body.jinja == "ran"
    assert not [f for f in body.findings if f.rule_id.startswith("jinja-")]


async def test__lint_endpoint__static_outcome_findings_join_the_problems_panel(stand: Stand) -> None:
    ws, _ = await folder_with_draft(stand)
    await edit_manifest(stand, ws, _VISIBLE_IF, 'equals: "maybe"')

    resp = await stand.client.post(
        f"{API}/workspaces/{ws}/lint", json={"path": "hse-cs-se/templates/vkr/versions/2026.1.9/version.yaml"}
    )

    assert resp.status_code == 200, resp.text
    report = resp.json()
    outcome = [f for f in report["findings"] if f["check"] == "outcome"]
    rules = {f["message"].split("]")[0].lstrip("[") for f in outcome}
    assert {"visible-if-value-not-in-options", "translation-missing"} <= rules
    error = next(f for f in outcome if "[visible-if-value-not-in-options]" in f["message"])
    assert error["severity"] == "error"
    assert error["line"]
    assert error["pointer"]
    assert error["path"] == "hse-cs-se/templates/vkr/versions/2026.1.9/version.yaml"
    # Расчётных правил здесь нет: они идут отдельным запросом.
    assert not any("[route-step-without-person]" in f["message"] for f in outcome)
    assert report["errors"] >= 1


async def test__lint_endpoint__released_version_outcome_errors_are_warnings(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await stand.client.post(
        f"{API}/workspaces/{ws}/lint", json={"path": "hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml"}
    )

    report = resp.json()
    outcome = [f for f in report["findings"] if f["check"] == "outcome"]
    assert outcome
    assert {f["severity"] for f in outcome} == {"warning"}


async def test__errors__missing_version_head_without_git_and_a_closed_section(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    missing = await _lint(stand, ws, ("hse-cs-sse", "coursework", "9.9.9"))
    head = await _lint(stand, ws, COURSEWORK, state="head")
    bad_state = await _lint(stand, ws, COURSEWORK, state="tail")
    off = await stand.client.put(f"{API}/section", json={"enabled": False})
    closed = await _lint(stand, ws, COURSEWORK)

    assert missing.status_code == 404
    assert (head.status_code, head.json()["code"], head.json()["reason"]) == (409, "diff_base_unavailable", "no_git")
    assert bad_state.status_code == 422
    assert off.status_code == 200
    assert (closed.status_code, closed.json()["code"]) == (404, "pack_studio_disabled")


async def test__jinja_on_a_non_work_tree_state_is_unavailable_and_not_an_error(stand: Stand) -> None:
    from .test_outcome_git import _ready  # noqa: PLC0415

    _, ws = await _ready(stand)

    head = _parse(await _lint(stand, ws, COURSEWORK, state="head", jinja="true"))

    assert head.state == "head"
    assert head.jinja == "unavailable"
    assert head.coverage.rows_total == 12


async def test__rate__seventh_request_in_a_minute_is_refused_with_retry_after(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    app = stand.client._transport.app  # type: ignore[attr-defined]
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.rate_limit_scale = 1.0
    await _lint(stand, ws, COURSEWORK)

    start = time.perf_counter()
    answers = [await _lint(stand, ws, COURSEWORK) for _ in range(8)]

    if time.perf_counter() - start < 60:
        refused = [r for r in answers if r.status_code == 429]
        assert refused
        assert refused[0].json()["code"] == "rate_limited"
        assert int(refused[0].headers["Retry-After"]) > 0
    assert answers[0].status_code == 200
