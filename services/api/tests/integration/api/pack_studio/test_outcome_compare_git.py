"""«До и после», матрица и сравнение состояний над git пространства (template-studio-outcome.md, 4.2 и 4.5, срез O7).

Репозиторий паков это голый репозиторий по file:// с папкой `packs/` внутри большого репозитория, клон частичный и
разреженный. База и последний коммит читаются из хранилища без checkout; рабочее дерево с несохранёнными правками
это то, что автор видит в Студии. Версии настоящие: черновики 2026.1.9 курсового проекта `hse-cs-sse` и ВКР `hse-cs-se`
(копии выпущенных версий, которые можно править), стартовые сценарии паков."""

from __future__ import annotations

import tempfile
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from hse_doc_studio.core.pack_studio.outcome.scenarios import parse_scenario
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.core.pack_studio.protocols import IPackWorkspaceRepository
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.atlas import build_atlas
from hse_doc_studio.use_cases.pack_studio.outcome.compare import (
    VersionSide,
    atlas_impact,
    impact_body,
    scenario_impacts,
)
from hse_doc_studio.use_cases.pack_studio.outcome_compare import PackCompareService
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService

from tests.fixtures.git_remote import BareRemote, make_bare_remote, seed_remote

from .conftest import API, Stand
from .outcome_compare_support import (
    ANNOTATION_AFTER,
    ANNOTATION_BEFORE,
    DRAFT,
    DRAFT_ANNOTATION,
    DRAFT_COURSEWORK,
    DRAFT_COURSEWORK_MANIFEST,
    SLOT_AFTER,
    SLOT_BEFORE,
    draft_coursework_files,
    edit_file,
    parse_compare,
    parse_impact,
    parse_matrix,
    post_op,
    real_scenario_files,
)
from .outcome_support import DRAFT_VKR, draft_vkr_files, real_files
from .scenario_support import COURSEWORK_TEMPLATE, VKR_TEMPLATE, put_scenario, scenario_body
from .test_git_workspace import _git_workspace

TODAY = date(2026, 11, 16)
_PROFILE = {"name": "Анна Иванова", "email": "anna@example.org"}
_COMPANY = {"supervisor": "company", "co_supervisor": "yes"}


def _remote(root: Path) -> BareRemote:
    remote = make_bare_remote(root / "packs.git")
    remote.git("config", "uploadpack.allowFilter", "true")
    files = {**real_files(), **draft_vkr_files(), **draft_coursework_files(), **real_scenario_files()}
    payload: dict[str, str | bytes] = {f"packs/{p}": d for p, d in files.items()}
    payload["README.md"] = "Репозиторий паков\n"
    payload["services/api/big.txt"] = "x" * 10_000
    seed_remote(remote, payload)
    return remote


async def _ready(stand: Stand) -> tuple[BareRemote, str]:
    remote = _remote(stand.root)
    resp = await stand.client.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    ws = await _git_workspace(stand, remote)
    assert ws["state"] == "ready", ws
    return remote, str(ws["id"])


@pytest.fixture
async def services(stand: Stand, monkeypatch: pytest.MonkeyPatch) -> PackCompareService:
    assert stand.container is not None
    outcome = await stand.container.get(PackOutcomeService)
    monkeypatch.setattr(outcome, "_today", lambda: TODAY)
    return await stand.container.get(PackCompareService)


def _drafts(tmp: Path, edit: tuple[str, str] | None) -> tuple[Any, Any]:
    """Черновик курсового проекта до и после правки условия слота: две версии, загруженные с диска (независимый
    расчёт, с которым сверяются ответы)."""
    for name in ("before", "after"):
        for rel, data in {**draft_coursework_files(), **real_scenario_files()}.items():
            target = tmp / name / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if edit is not None:
        path = tmp / "after" / DRAFT_COURSEWORK_MANIFEST
        path.write_text(path.read_text(encoding="utf-8").replace(*edit, 1), encoding="utf-8")
    ref = DRAFT_COURSEWORK
    old = YamlTemplateRepository(tmp / "before").get_version(*ref)
    new = YamlTemplateRepository(tmp / "after").get_version(*ref)
    assert old is not None
    assert new is not None
    return old, new


def _side(version: Any) -> VersionSide:
    return VersionSide(version, tuple(auto_examples(version)))


def _starter(template: str) -> dict[str, Any]:
    return {
        Path(p).stem: parse_scenario(d.decode("utf-8"))
        for p, d in real_scenario_files().items()
        if f"/templates/{template}/" in p
    }


# ── до и после правки слота ──────────────────────────────────────────────────


async def test__impact__nothing_edited__no_scenario_and_no_atlas_row_changes(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)

    got = parse_impact(await post_op(stand, ws, DRAFT_COURSEWORK, "impact"))

    starters = len(_starter("coursework"))
    assert (got.summary.scenarios_total, got.summary.scenarios_changed, got.summary.scenarios_error) == (starters, 0, 0)
    assert starters > 0
    assert got.summary.sections == []
    assert got.summary.atlas is not None
    assert got.summary.atlas.rows_changed == 0
    assert got.summary.atlas.outcomes_before == got.summary.atlas.outcomes_after
    assert got.base_revision == got.work_tree_revision
    assert all(s.status == "unchanged" and s.changes == [] for s in got.scenarios)
    assert got.new_findings == []


async def test__impact__unsaved_slot_edit__changes_exactly_what_a_direct_calculation_says(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)
    await edit_file(stand, ws, f"packs/{DRAFT_COURSEWORK_MANIFEST}".removeprefix("packs/"), SLOT_BEFORE, SLOT_AFTER)

    resp = await post_op(stand, ws, DRAFT_COURSEWORK, "impact")

    got = parse_impact(resp)
    with tempfile.TemporaryDirectory() as tmp:
        old, new = _drafts(Path(tmp), (SLOT_BEFORE, SLOT_AFTER))
        impacts = scenario_impacts(_side(old), _side(new), _starter("coursework"), TODAY)
        example = auto_examples(old)[0]
        atlas = atlas_impact(
            _plain(build_atlas(new, auto_examples(new)[0], TODAY)),
            _plain(build_atlas(old, example, TODAY)),
            old,
            example,
            TODAY,
        )
    direct = impact_body(impacts, atlas)
    assert resp.json()["summary"] == direct["summary"]
    assert resp.json()["scenarios"] == direct["scenarios"]
    assert got.summary.scenarios_changed == 1
    assert {s.scenario: s.status for s in got.scenarios} == {
        "company-supervisor": "unchanged",
        "no-supervisor": "unchanged",
        "university-supervisor": "changed",
    }
    assert got.base_revision != got.work_tree_revision
    assert got.summary.atlas is not None
    assert 0 < got.summary.atlas.rows_changed < got.summary.atlas.rows_total
    changed = next(s for s in got.scenarios if s.status == "changed")
    assert {(c.symbol, c.kind) for c in changed.changes} == {
        ("+", "route_step"),
        ("+", "route_pair"),
        ("-", "skipped_pair"),
    }
    assert all(any(r.kind == "slot_when" for r in c.why) for c in changed.changes if c.kind != "route_step")


def _plain(atlas: Any) -> dict[str, Any]:
    from hse_doc_studio.core.pack_studio.outcome.payload import to_json  # noqa: PLC0415

    return dict(to_json(atlas))


async def test__impact__head_after_a_commit_is_clean_and_base_still_shows_the_change(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)
    await edit_file(stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)
    vs_head = parse_impact(
        await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"base": "head", "include_atlas": False})
    )
    committed = await stand.client.post(f"{API}/workspaces/{ws}/git/commit", json={})
    assert committed.status_code == 200, committed.text

    clean = parse_impact(await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"base": "head", "include_atlas": False}))
    vs_base = parse_impact(
        await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"base": "base", "include_atlas": False})
    )

    assert vs_head.summary.scenarios_changed == 1
    assert clean.summary.scenarios_changed == 0
    assert clean.summary.atlas is None
    assert vs_base.summary.scenarios_changed == 1
    assert vs_base.base == "base"


async def test__impact__scenario_selection_and_unknown_scenario(stand: Stand, services: PackCompareService) -> None:
    _, ws = await _ready(stand)
    await edit_file(stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)

    one = parse_impact(
        await post_op(
            stand, ws, DRAFT_COURSEWORK, "impact", {"scenarios": ["company-supervisor"], "include_atlas": False}
        )
    )
    ghost = await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"scenarios": ["ghost"]})

    assert [s.scenario for s in one.scenarios] == ["company-supervisor"]
    assert one.summary.scenarios_changed == 0
    assert (ghost.status_code, ghost.json()["code"]) == (404, "scenario_not_found")


async def test__impact__document_condition_edit_in_the_vkr_draft(stand: Stand, services: PackCompareService) -> None:
    _, ws = await _ready(stand)
    await edit_file(stand, ws, DRAFT_ANNOTATION, ANNOTATION_BEFORE, ANNOTATION_AFTER)
    started = time.perf_counter()

    got = parse_impact(await post_op(stand, ws, DRAFT_VKR, "impact", {"include_atlas": False}))

    elapsed = time.perf_counter() - started
    assert {s.scenario: s.status for s in got.scenarios} == {
        "nda-programmer-manual-only": "unchanged",
        "research-company-supervisor": "unchanged",
        "solo-university-supervisor": "unchanged",
        "team-of-three-nda": "changed",
    }
    changed = next(s for s in got.scenarios if s.status == "changed")
    assert ("+", "shared_annotation") in {(c.symbol, c.id) for c in changed.changes if c.section == "documents"}
    assert {d.section for d in got.summary.sections} >= {"documents", "points"}
    assert elapsed < 20, elapsed


async def test__impact__atlas_of_the_vkr_is_included_and_counts_the_changed_rows(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)
    await edit_file(stand, ws, DRAFT_ANNOTATION, ANNOTATION_BEFORE, ANNOTATION_AFTER)
    started = time.perf_counter()

    got = parse_impact(await post_op(stand, ws, DRAFT_VKR, "impact"))

    elapsed = time.perf_counter() - started
    assert got.summary.atlas is not None
    assert got.summary.atlas.rows_total == 864
    assert 0 < got.summary.atlas.rows_changed < 864
    # Две таблицы атласа и строки на базе: у каждой части свой срок 20 с; общий предел здесь только на здравый смысл.
    assert elapsed < 90, elapsed


async def test__impact__input_removed_by_the_edit_breaks_that_scenario_and_names_the_side(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)
    added = await put_scenario(stand, ws, VKR_TEMPLATE, "english", scenario_body("По-английски", {"lang": "en"}))
    assert added.status_code == 200, added.text
    await edit_file(
        stand, ws, "hse-cs-se/templates/vkr/versions/2026.1.9/version.yaml", "langs: [ru, en]", "langs: [ru]"
    )

    got = parse_impact(await post_op(stand, ws, DRAFT_VKR, "impact", {"include_atlas": False}))

    english = next(s for s in got.scenarios if s.scenario == "english")
    assert english.status == "error"
    assert (english.message or "").startswith("work_tree: lang=")
    assert got.summary.scenarios_error == 1
    assert got.summary.scenarios_total == len(_starter("vkr")) + 1


async def test__impact__a_scenario_that_exists_only_in_the_work_tree_is_compared_too(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)
    await put_scenario(stand, ws, COURSEWORK_TEMPLATE, "mine", scenario_body("Мой", {"supervisor": "university"}))
    await edit_file(stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)

    got = parse_impact(await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"include_atlas": False}))

    mine = next(s for s in got.scenarios if s.scenario == "mine")
    assert mine.status == "changed"
    assert got.summary.scenarios_total == len(_starter("coursework")) + 1


# ── база отсутствует ─────────────────────────────────────────────────────────


async def test__impact__no_base_branch__base_is_unavailable_but_head_works(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)
    assert stand.container is not None
    repo = await stand.container.get(IPackWorkspaceRepository)
    found = await repo.get(UUID(ws), None)
    assert found is not None
    await repo.update(replace(found, base_branch=None))

    base = await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"base": "base"})
    head = await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"base": "head", "include_atlas": False})
    matrix = await post_op(stand, ws, DRAFT_COURSEWORK, "matrix", {"against": "base"})

    assert (base.status_code, base.json()["code"], base.json()["reason"]) == (409, "diff_base_unavailable", "no_base")
    assert head.status_code == 200
    assert (matrix.status_code, matrix.json()["reason"]) == (409, "no_base")


async def test__impact__new_version_has_no_base__new_version(stand: Stand, services: PackCompareService) -> None:
    _, ws = await _ready(stand)
    new = ("hse-cs-sse", "coursework", "2026.1.10")
    manifest = f"hse-cs-sse/templates/coursework/versions/{new[2]}/version.yaml"
    created = await stand.client.put(
        stand.file_url(ws, manifest),
        content=draft_coursework_files()[DRAFT_COURSEWORK_MANIFEST].replace(
            f'id: "{DRAFT}"'.encode(), f'id: "{new[2]}"'.encode(), 1
        ),
    )
    assert created.status_code == 200, created.text
    # Файлы версии лежат в рабочем дереве, ни в коммите, ни в базе их нет.
    for rel, data in draft_coursework_files().items():
        if "/files/" in rel or "/checks/" in rel:
            moved = rel.replace(f"/versions/{DRAFT}/", f"/versions/{new[2]}/")
            await stand.client.put(stand.file_url(ws, moved), content=data)

    impact = await post_op(stand, ws, new, "impact", {"include_atlas": False})
    matrix = await post_op(stand, ws, new, "matrix", {"against": "base"})
    work = await post_op(stand, ws, new, "matrix")
    compare = await post_op(stand, ws, new, "compare", {"left": {"state": "base"}, "right": {}})

    for resp in (impact, matrix, compare):
        assert resp.status_code == 409, resp.text
        assert (resp.json()["code"], resp.json()["reason"]) == ("diff_base_unavailable", "new_version")
    assert work.status_code == 200, work.text


# ── матрица и сравнение состояний ────────────────────────────────────────────


async def test__matrix__against_base__only_the_edited_cell_is_marked(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)
    clean = parse_matrix(await post_op(stand, ws, DRAFT_COURSEWORK, "matrix", {"against": "base"}))
    await edit_file(stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)

    got = parse_matrix(await post_op(stand, ws, DRAFT_COURSEWORK, "matrix", {"against": "base"}))

    assert all(c.changed is False for r in clean.rows for c in r.cells)
    marked = {r.scenario: [c.section for c in r.cells if c.changed] for r in got.rows}
    assert marked == {"company-supervisor": [], "no-supervisor": [], "university-supervisor": ["route"]}
    university = next(r for r in got.rows if r.scenario == "university-supervisor")
    assert university.status == "failed"  # утверждение про маршрут записано до правки
    assert next(c for c in university.cells if c.section == "route").status == "changed"


async def test__matrix__head_state_reads_the_commit_not_the_work_tree(
    stand: Stand, services: PackCompareService
) -> None:
    _, ws = await _ready(stand)
    await edit_file(stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)

    work = parse_matrix(await post_op(stand, ws, DRAFT_COURSEWORK, "matrix"))
    head = parse_matrix(await post_op(stand, ws, DRAFT_COURSEWORK, "matrix", {"state": "head"}))

    assert {r.status for r in head.rows} == {"passed"}
    assert {r.scenario: r.status for r in work.rows}["university-supervisor"] == "failed"
    assert head.revision != work.revision
    assert head.state == "head"


async def test__compare__one_combination_between_the_states(stand: Stand, services: PackCompareService) -> None:
    _, ws = await _ready(stand)
    clean = parse_compare(
        await post_op(
            stand,
            ws,
            DRAFT_COURSEWORK,
            "compare",
            {
                "left": {"state": "base", "inputs": {"supervisor": "university"}},
                "right": {"inputs": {"supervisor": "university"}},
            },
        )
    )
    await edit_file(stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)
    body = {
        "left": {"state": "base", "scenario": "university-supervisor"},
        "right": {"state": "work_tree", "scenario": "university-supervisor"},
    }

    edited = parse_compare(await post_op(stand, ws, DRAFT_COURSEWORK, "compare", body))
    against_head = parse_compare(
        await post_op(stand, ws, DRAFT_COURSEWORK, "compare", {**body, "left": {**body["left"], "state": "head"}})
    )
    company = parse_compare(
        await post_op(
            stand,
            ws,
            DRAFT_COURSEWORK,
            "compare",
            {"left": {"state": "base", "inputs": _COMPANY}, "right": {"inputs": _COMPANY}},
        )
    )

    assert clean.identical
    assert (edited.left.state, edited.right.state) == ("base", "work_tree")
    assert edited.left.revision != edited.right.revision
    assert {(c.symbol, c.kind) for c in edited.changes} == {
        ("+", "route_step"),
        ("+", "route_pair"),
        ("-", "skipped_pair"),
    }
    assert against_head.changes == edited.changes
    assert company.identical


async def test__etag__follows_the_work_tree_and_the_base(stand: Stand, services: PackCompareService) -> None:
    remote, ws = await _ready(stand)
    first = await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"include_atlas": False})
    stable = await post_op(
        stand, ws, DRAFT_COURSEWORK, "impact", {"include_atlas": False}, **{"If-None-Match": first.headers["ETag"]}
    )
    await edit_file(stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)

    edited = await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"include_atlas": False})
    stale = await post_op(
        stand, ws, DRAFT_COURSEWORK, "impact", {"include_atlas": False}, **{"If-None-Match": first.headers["ETag"]}
    )
    seed_remote(
        remote,
        {
            f"packs/{DRAFT_COURSEWORK_MANIFEST}": draft_coursework_files()[DRAFT_COURSEWORK_MANIFEST].replace(
                SLOT_BEFORE.encode(), SLOT_AFTER.encode()
            )
        },
        message="base moved",
    )
    refreshed = await stand.client.post(f"{API}/workspaces/{ws}/refresh")
    assert refreshed.status_code == 202, refreshed.text
    await stand.settled(ws)
    moved = await post_op(stand, ws, DRAFT_COURSEWORK, "impact", {"include_atlas": False})

    assert (first.status_code, stable.status_code) == (200, 304)
    assert edited.headers["ETag"] != first.headers["ETag"]
    assert stale.status_code == 200
    # База ушла вперёд и стала такой же, как рабочее дерево: ETag новый, изменений нет.
    assert moved.headers["ETag"] not in {first.headers["ETag"], edited.headers["ETag"]}
    assert parse_impact(moved).summary.scenarios_changed == 0


async def test__all_three__never_write_anything_to_the_workspace(stand: Stand, services: PackCompareService) -> None:
    _, ws = await _ready(stand)
    await edit_file(stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)
    before = await stand.client.get(f"{API}/workspaces/{ws}/git")

    await post_op(stand, ws, DRAFT_COURSEWORK, "impact")
    await post_op(stand, ws, DRAFT_COURSEWORK, "matrix", {"against": "base"})
    await post_op(stand, ws, DRAFT_COURSEWORK, "compare", {"left": {"state": "base"}, "right": {}})

    after = await stand.client.get(f"{API}/workspaces/{ws}/git")
    assert after.json() == before.json()
    assert before.json()["uncommitted"], "правка осталась несохранённой: запросы ничего не коммитят и не откатывают"
