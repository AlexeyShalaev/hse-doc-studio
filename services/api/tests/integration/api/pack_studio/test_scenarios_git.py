"""Сценарии над git пространства: `work_tree`, `head`, `base` (template-studio-outcome.md, 4.2 и 5, срез O6).

Репозиторий паков это голый репозиторий по file:// с папкой `packs/` внутри большого репозитория, клон частичный и
разреженный (как у официальных паков). Файлы сценариев читаются из коммита без checkout тем же путём, что версия
(`revision_files` с префиксами вне каталога версии); сценарий в рабочем дереве и в коммите это разные состояния."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.pack_studio.outcome.scenarios import ParticipantAssertion, Scenario, scenario_text

from tests.fixtures.git_remote import BareRemote, make_bare_remote, seed_remote

from .conftest import API, Stand
from .outcome_support import (
    DRAFT_MANIFEST,
    DRAFT_VKR,
    draft_vkr_files,
    parse_outcome,
    post_outcome,
    real_files,
)
from .scenario_support import (
    VKR_TEMPLATE,
    list_scenarios,
    parse_entry,
    parse_list,
    parse_run,
    put_scenario,
    run_scenarios,
    scenario_body,
    scenario_path,
    scenarios_url,
)
from .test_git_workspace import _git_workspace

_PROFILE = {"name": "Анна Иванова", "email": "anna@example.org"}
_NEW_MANIFEST = "hse-cs-se/templates/vkr/versions/2026.1.10/version.yaml"
_COMPANY = {"supervisor": "company", "co_supervisor": "yes"}


def _scenario_file(name: str, inputs: dict[str, str], *, co_supervisor: bool = True) -> str:
    return scenario_text(
        Scenario(
            name={"ru": name},
            inputs=inputs,
            versions=("2026.1.*",),
            assertions=(ParticipantAssertion(persona="co_supervisor", present=co_supervisor),),
        )
    )


COMMITTED = _scenario_file("Из коммита", _COMPANY)
_COMMITTED_PATH = f"packs/{scenario_path(VKR_TEMPLATE, 'committed')}"


def _remote(root: Path, extra: dict[str, str | bytes] | None = None) -> BareRemote:
    remote = make_bare_remote(root / "packs.git")
    remote.git("config", "uploadpack.allowFilter", "true")
    payload: dict[str, str | bytes] = {f"packs/{p}": d for p, d in {**real_files(), **draft_vkr_files()}.items()}
    payload["README.md"] = "Репозиторий паков\n"
    payload["services/api/big.txt"] = "x" * 10_000
    payload[_COMMITTED_PATH] = COMMITTED
    payload.update(extra or {})
    seed_remote(remote, payload)
    return remote


async def _ready(stand: Stand, extra: dict[str, str | bytes] | None = None) -> tuple[BareRemote, str]:
    remote = _remote(stand.root, extra)
    resp = await stand.client.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    ws = await _git_workspace(stand, remote)
    assert ws["state"] == "ready", ws
    return remote, str(ws["id"])


def _ids(resp: object) -> list[str]:
    return [e.id for e in parse_list(resp).scenarios]  # type: ignore[arg-type]


async def test__fresh_clone__scenario_from_the_commit_is_seen_in_all_three_states(stand: Stand) -> None:
    _, ws = await _ready(stand)

    for state in ("work_tree", "head", "base"):
        listed = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE, state))
        assert [e.id for e in listed.scenarios] == ["committed"], state
        (entry,) = listed.scenarios
        assert entry.error is None
        assert entry.path == scenario_path(VKR_TEMPLATE, "committed")
        assert entry.scenario is not None
        assert entry.scenario.inputs == _COMPANY
    etags = {
        parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE, s)).scenarios[0].etag
        for s in ("work_tree", "head", "base")
    }
    assert len(etags) == 1, "байты те же, ETag файла тот же в любом состоянии"


@pytest.mark.timeout(180)
async def test__fresh_clone__run_in_three_states_gives_the_same_result_with_its_own_etag(stand: Stand) -> None:
    _, ws = await _ready(stand)

    answers = {
        state: await run_scenarios(stand, ws, VKR_TEMPLATE, {"state": state}) for state in ("work_tree", "head", "base")
    }

    parsed = {state: parse_run(resp) for state, resp in answers.items()}
    assert {state: run.state for state, run in parsed.items()} == {s: s for s in answers}
    assert {run.version for run in parsed.values()} == {"2026.1.9"}
    assert [r.status for r in parsed["head"].results] == ["passed"]
    bodies = [{k: v for k, v in r.json().items() if k != "state"} for r in answers.values()]
    assert bodies[0] == bodies[1] == bodies[2]
    assert len({resp.headers["ETag"] for resp in answers.values()}) == 3
    again = await run_scenarios(
        stand, ws, VKR_TEMPLATE, {"state": "head"}, **{"If-None-Match": answers["head"].headers["ETag"]}
    )
    assert again.status_code == 304


@pytest.mark.timeout(120)
async def test__uncommitted_scenario_edits__work_tree_changes_head_and_base_stay(stand: Stand) -> None:
    _, ws = await _ready(stand)
    committed = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE, "head")).scenarios[0]

    new = await put_scenario(stand, ws, VKR_TEMPLATE, "local-only", scenario_body("Только у меня", _COMPANY))
    edited = await put_scenario(
        stand,
        ws,
        VKR_TEMPLATE,
        "committed",
        scenario_body(
            "Правка",
            {"supervisor": "university"},
            versions=["2026.1.*"],
            assertions=[{"kind": "participant_present", "persona": "co_supervisor", "present": False}],
        ),
        if_match=committed.etag,
    )

    assert new.status_code == 200
    assert edited.status_code == 200
    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "work_tree")) == ["committed", "local-only"]
    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "head")) == ["committed"]
    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "base")) == ["committed"]
    head_entry = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE, "head")).scenarios[0]
    assert head_entry.etag == committed.etag
    work = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"state": "work_tree"}))
    head = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"state": "head"}))
    assert [r.scenario for r in work.results] == ["committed", "local-only"]
    assert [r.scenario for r in head.results] == ["committed"]
    assert [r.status for r in work.results] == ["passed", "unchecked"]


async def test__outcome_with_a_scenario__reads_the_scenario_of_the_requested_state(stand: Stand) -> None:
    _, ws = await _ready(stand)
    committed = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE, "head")).scenarios[0]
    await put_scenario(
        stand, ws, VKR_TEMPLATE, "committed", scenario_body("Правка", {"supervisor": "none"}), if_match=committed.etag
    )

    work = parse_outcome(await post_outcome(stand, ws, DRAFT_VKR, {"scenario": "committed"}))
    head = parse_outcome(await post_outcome(stand, ws, DRAFT_VKR, {"scenario": "committed", "state": "head"}))
    base = parse_outcome(await post_outcome(stand, ws, DRAFT_VKR, {"scenario": "committed", "state": "base"}))

    assert work.inputs["supervisor"] == "none"
    assert (head.inputs["supervisor"], head.inputs["co_supervisor"]) == ("company", "yes")
    assert base.inputs == head.inputs
    only_local = await put_scenario(stand, ws, VKR_TEMPLATE, "local-only", scenario_body("Локальный"))
    assert only_local.status_code == 200
    missing = await post_outcome(stand, ws, DRAFT_VKR, {"scenario": "local-only", "state": "head"})
    assert (missing.status_code, missing.json()["code"]) == (404, "scenario_not_found")
    assert (await post_outcome(stand, ws, DRAFT_VKR, {"scenario": "local-only"})).status_code == 200


async def test__commit__moves_head_with_the_scenario_but_not_base(stand: Stand) -> None:
    _, ws = await _ready(stand)
    await put_scenario(stand, ws, VKR_TEMPLATE, "to-commit", scenario_body("К коммиту", _COMPANY))
    status = (await stand.client.get(f"{API}/workspaces/{ws}/git")).json()
    assert [c["path"] for c in status["uncommitted"]] == [scenario_path(VKR_TEMPLATE, "to-commit")]

    committed = await stand.client.post(f"{API}/workspaces/{ws}/git/commit", json={})

    assert committed.status_code == 200, committed.text
    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "head")) == ["committed", "to-commit"]
    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "base")) == ["committed"]


async def test__base_moved_on_the_server__refresh_moves_base_scenarios_and_keeps_head(stand: Stand) -> None:
    remote, ws = await _ready(stand)
    seed_remote(
        remote,
        {
            f"packs/{scenario_path(VKR_TEMPLATE, 'from-server')}": _scenario_file(
                "С сервера", {"supervisor": "none"}, co_supervisor=False
            )
        },
        message="scenario on the server",
    )
    refreshed = await stand.client.post(f"{API}/workspaces/{ws}/refresh")
    assert refreshed.status_code == 202, refreshed.text
    assert (await stand.settled(ws))["base_sha"] == remote.head("main")

    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "base")) == ["committed", "from-server"]
    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "head")) == ["committed"]
    base = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"state": "base"}))
    assert [(r.scenario, r.status) for r in base.results] == [("committed", "passed"), ("from-server", "passed")]


async def test__soft_delete__the_file_leaves_the_work_tree_and_stays_in_head_so_the_same_bytes_come_back(
    stand: Stand,
) -> None:
    _, ws = await _ready(stand)
    head_entry = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE, "head")).scenarios[0]

    deleted = await stand.client.delete(
        scenarios_url(ws, VKR_TEMPLATE, "/committed"), headers={"If-Match": head_entry.etag}
    )

    assert deleted.status_code == 204
    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "work_tree")) == []
    assert _ids(await list_scenarios(stand, ws, VKR_TEMPLATE, "head")) == ["committed"]
    status = (await stand.client.get(f"{API}/workspaces/{ws}/git")).json()
    assert [(c["path"], c["status"]) for c in status["uncommitted"]] == [
        (scenario_path(VKR_TEMPLATE, "committed"), "deleted")
    ]
    # «Отменить»: сценарий пишется заново из того, что вернул список (head), файл совпадает с коммитом байт в байт.
    assert head_entry.scenario is not None
    restored = await put_scenario(
        stand, ws, VKR_TEMPLATE, "committed", {"scenario": head_entry.scenario.model_dump(mode="json")}
    )
    assert parse_entry(restored).etag == head_entry.etag
    assert (await stand.client.get(f"{API}/workspaces/{ws}/git")).json()["uncommitted"] == []
    read = await stand.read(ws, scenario_path(VKR_TEMPLATE, "committed"))
    assert read.content.decode("utf-8") == COMMITTED


async def test__new_version_in_the_work_tree__default_run_takes_it_and_head_says_new_version(stand: Stand) -> None:
    _, ws = await _ready(stand)
    created = await stand.client.put(
        stand.file_url(ws, _NEW_MANIFEST), content=b'id: "2026.1.10"\nstatus: beta\nlangs: [ru]\n'
    )
    assert created.status_code == 200, created.text

    work = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE))
    head = await run_scenarios(stand, ws, VKR_TEMPLATE, {"state": "head"})
    head_old = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"state": "head", "version": "2026.1.9"}))

    assert work.version == "2026.1.10"
    assert (head.status_code, head.json()["code"], head.json()["reason"]) == (
        409,
        "diff_base_unavailable",
        "new_version",
    )
    assert head_old.version == "2026.1.9"
    assert [r.status for r in head_old.results] == ["passed"]


async def test__record_snapshot_on_head__is_the_result_of_the_committed_version_not_of_the_unsaved_edit(
    stand: Stand,
) -> None:
    _, ws = await _ready(stand)
    manifest = (await stand.read(ws, DRAFT_MANIFEST)).content.decode("utf-8")
    signed = "signatures: [author, supervisor]"
    assert signed in manifest
    read = await stand.read(ws, DRAFT_MANIFEST)
    written = await stand.client.put(
        stand.file_url(ws, DRAFT_MANIFEST),
        content=manifest.replace(signed, "signatures: [author]", 1).encode("utf-8"),
        headers={"If-Match": read.headers["ETag"]},
    )
    assert written.status_code == 200, written.text
    body = scenario_body("Снимок", {"kind": "research"}, versions=["2026.1.*"])

    on_head = parse_entry(await put_scenario(stand, ws, VKR_TEMPLATE, "snap-head", {**body, "record_snapshot": "head"}))
    on_work = parse_entry(
        await put_scenario(stand, ws, VKR_TEMPLATE, "snap-work", {**body, "record_snapshot": "work_tree"})
    )

    assert on_head.scenario is not None
    assert on_work.scenario is not None
    assert on_head.scenario.snapshot is not None
    assert on_work.scenario.snapshot is not None
    head_digest = parse_outcome(
        await post_outcome(stand, ws, DRAFT_VKR, {"state": "head", "inputs": {"kind": "research"}})
    ).digest
    work_digest = parse_outcome(await post_outcome(stand, ws, DRAFT_VKR, {"inputs": {"kind": "research"}})).digest
    assert on_head.scenario.snapshot == head_digest
    assert on_work.scenario.snapshot == work_digest
    assert head_digest != work_digest
    # Прогон на `work_tree`: снимок с `head` теперь расходится, снимок с `work_tree` совпадает.
    run = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"scenarios": ["snap-head", "snap-work"]}))
    assert {r.scenario: r.status for r in run.results} == {"snap-head": "failed", "snap-work": "passed"}
