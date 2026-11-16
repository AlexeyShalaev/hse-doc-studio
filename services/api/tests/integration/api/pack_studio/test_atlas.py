"""Атлас результата версии (срез O4, раздел 4.4 дизайна результата) в локальной Студии и над git пространства.

Настоящие роутер, DI и чтение версий; версии настоящие (ВКР `hse-cs-se` 2026.1.2, курсовой проект `hse-cs-sse`
2026.1.6) и черновик ВКР, который можно править. Проверяются числа дизайна, тело по строгой модели контракта, ETag
и 304, закрепления, ошибки кодами, три состояния версии и учёт несохранённой правки."""

from __future__ import annotations

from typing import Any

from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeAtlasResponse
from httpx import Response

from .conftest import Stand
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
from .test_outcome_git import _ready


async def _atlas(
    stand: Stand, ws: str, ref: tuple[str, str, str], *, pins: tuple[str, ...] = (), **params: str
) -> Response:
    query: list[tuple[str, str]] = [("pin", pin) for pin in pins] + list(params.items())
    return await stand.client.get(outcome_url(ws, ref, "/atlas"), params=query)


def _parse(resp: Response) -> PackOutcomeAtlasResponse:
    assert resp.status_code == 200, resp.text
    return PackOutcomeAtlasResponse.model_validate(resp.json())


def _distinct(atlas: PackOutcomeAtlasResponse, *sections: str) -> int:
    wanted = set(sections)
    return len({tuple(p.fingerprint for p in o.digest.sections if p.section in wanted) for o in atlas.outcomes})


# ── числа дизайна ────────────────────────────────────────────────────────────


async def test__vkr__rows_outcomes_and_ignored_inputs_are_the_documented_ones(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await _atlas(stand, ws, VKR)

    atlas = _parse(resp)
    assert (atlas.pack, atlas.template, atlas.version, atlas.state) == (*VKR, "work_tree")
    assert (atlas.combinations_total, atlas.rows_total, atlas.outcomes_distinct) == (5184, 864, 384)
    assert _distinct(atlas, "documents", "points", "route") == 24
    assert _distinct(atlas, "documents", "points", "route", "participants") == 192
    assert {(i.input, i.reason) for i in atlas.ignored} == {("lang", "cosmetic"), ("variant.presentation", "cosmetic")}
    assert [d.input for d in atlas.dimensions][:3] == ["kind", "staffing", "supervisor"]
    assert atlas.revision.startswith("sha256-")
    assert resp.headers["Cache-Control"] == "private, no-cache"
    assert resp.headers["ETag"].startswith('"')


async def test__coursework__four_routes_and_the_rules_that_read_each_dimension(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    atlas = _parse(await _atlas(stand, ws, COURSEWORK))

    assert (atlas.combinations_total, atlas.rows_total, atlas.outcomes_distinct) == (576, 12, 12)
    assert _distinct(atlas, "route") == 4
    assert _distinct(atlas, "documents") == 1
    by_input = {d.input: d for d in atlas.dimensions}
    assert list(by_input) == ["supervisor", "co_supervisor", "academic_supervisor"]
    assert by_input["supervisor"].rules[0].pointer == "/pack_submission/profiles/0/signing_slots/1/when"
    assert by_input["academic_supervisor"].rules == []


# ── ETag, закрепления, ошибки ────────────────────────────────────────────────


async def test__etag__if_none_match_answers_304_and_a_pin_has_its_own_etag(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    first = await _atlas(stand, ws, COURSEWORK)
    etag = first.headers["ETag"]

    same = await stand.client.get(outcome_url(ws, COURSEWORK, "/atlas"), headers={"If-None-Match": etag})
    pinned = await _atlas(stand, ws, COURSEWORK, pins=("supervisor:company",))

    assert same.status_code == 304
    assert same.headers["ETag"] == etag
    assert same.content == b""
    assert pinned.headers["ETag"] != etag
    assert _parse(pinned).rows_total == 4
    again = await stand.client.get(
        outcome_url(ws, COURSEWORK, "/atlas"),
        params=[("pin", "supervisor:company")],
        headers={"If-None-Match": pinned.headers["ETag"]},
    )
    assert again.status_code == 304


async def test__pins__cut_the_table_and_keep_the_pinned_input_as_a_one_valued_dimension(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    full = _parse(await _atlas(stand, ws, VKR))

    pinned = _parse(await _atlas(stand, ws, VKR, pins=("kind:research", "meta.nda:yes")))

    assert pinned.rows_total == full.rows_total // 4
    assert pinned.combinations_total == full.combinations_total
    kind = next(d for d in pinned.dimensions if d.input == "kind")
    assert (kind.values, kind.default) == (["research"], "research")
    assert all(row.key.startswith("research|") for row in pinned.rows)
    assert pinned.revision == full.revision


async def test__errors__are_coded(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    ref = COURSEWORK

    cases: dict[str, tuple[Response, str]] = {
        "nope": (await _atlas(stand, ws, ref, pins=("nope:x",)), "nope"),
        "supervisor": (await _atlas(stand, ws, ref, pins=("supervisor:boss",)), "supervisor"),
        "pin": (await _atlas(stand, ws, ref, pins=("supervisor",)), "pin"),
        "twice": (await _atlas(stand, ws, ref, pins=("supervisor:none", "supervisor:company")), "supervisor"),
        "example": (await _atlas(stand, ws, ref, example="missing"), "example"),
    }

    for name, (resp, field) in cases.items():
        assert resp.status_code == 400, (name, resp.text)
        assert resp.json()["code"] == "inputs_invalid"
        assert resp.json()["field"] == field
    missing = await _atlas(stand, ws, ("hse-cs-sse", "coursework", "9.9.9"))
    assert missing.status_code == 404, missing.text
    # Папка без git не имеет `head` и `base`.
    head = await _atlas(stand, ws, ref, state="head")
    assert (head.status_code, head.json()["code"], head.json()["reason"]) == (409, "diff_base_unavailable", "no_git")


# ── версии над git и несохранённая правка ────────────────────────────────────


async def test__git__head_and_base_give_the_same_atlas_with_their_own_etag(stand: Stand) -> None:
    _, ws = await _ready(stand)

    answers = {state: await _atlas(stand, ws, COURSEWORK, state=state) for state in ("work_tree", "head", "base")}
    parsed = {state: _parse(resp) for state, resp in answers.items()}

    assert {state: atlas.state for state, atlas in parsed.items()} == {s: s for s in answers}
    assert len({resp.headers["ETag"] for resp in answers.values()}) == 3
    bodies = [{k: v for k, v in r.json().items() if k not in {"state", "elapsed_ms"}} for r in answers.values()]
    assert bodies[0] == bodies[1] == bodies[2]
    assert parsed["head"].rows_total == 12


async def test__git__an_unsaved_edit_changes_the_work_tree_atlas_only(stand: Stand) -> None:
    _, ws = await _ready(stand)

    def lang(atlas: PackOutcomeAtlasResponse) -> str:
        return next(i.reason for i in atlas.ignored if i.input == "lang")

    before = _parse(await _atlas(stand, ws, DRAFT_VKR))
    assert lang(before) == "cosmetic"

    await edit_manifest(stand, ws, LANGS, "langs: [ru]")

    work = _parse(await _atlas(stand, ws, DRAFT_VKR))
    head = _parse(await _atlas(stand, ws, DRAFT_VKR, state="head"))
    assert (lang(work), lang(head)) == ("no_effect", "cosmetic")
    assert work.revision != head.revision
    assert work.rows_total == head.rows_total == 864


async def test__draft__an_edit_between_requests_changes_the_etag(stand: Stand) -> None:
    ws, _ = await folder_with_draft(stand)
    first = await _atlas(stand, ws, DRAFT_VKR)

    await edit_manifest(stand, ws, LANGS, "langs: [ru]")
    second = await stand.client.get(
        outcome_url(ws, DRAFT_VKR, "/atlas"), headers={"If-None-Match": first.headers["ETag"]}
    )

    assert second.status_code == 200, second.text
    assert second.headers["ETag"] != first.headers["ETag"]
    body: dict[str, Any] = second.json()
    assert body["revision"] != first.json()["revision"]
