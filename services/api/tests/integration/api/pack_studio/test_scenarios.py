"""Сценарии шаблона по HTTP (template-studio-outcome.md, разделы 4.6 и 5, срез O6) в локальной Студии над папкой.

Настоящие роутер и DI, настоящие версии репозитория (ВКР `hse-cs-se` 2026.1.2, курсовой проект `hse-cs-sse` 2026.1.6) и
черновик ВКР `2026.1.9`, который можно править. Ответы принимают строгие модели контракта. Состояния `head` и `base`
над git: `test_scenarios_git.py`."""

from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.pack_studio.outcome.scenarios import parse_scenario, scenario_text
from hse_doc_studio.infra.ratelimit.memory import InMemoryRateLimiter
from hse_doc_studio.use_cases.pack_studio import scenario_service
from hse_doc_studio.use_cases.pack_studio.outcome import scenario_runner
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService
from hse_doc_studio.use_cases.pack_studio.scenario_service import PackScenarioService

from .conftest import API, Stand
from .outcome_support import (
    COURSEWORK,
    DRAFT_VKR,
    REAL_PACKS,
    VKR,
    edit_manifest,
    folder_with_draft,
    folder_with_real_packs,
    get_inputs,
    outcome_url,
    parse_outcome,
    post_outcome,
)
from .scenario_support import (
    COURSEWORK_TEMPLATE,
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
    tree_digest,
)

TODAY = date(2026, 11, 16)
COMPANY = {"supervisor": "company", "co_supervisor": "yes"}
CHECKPOINT_PAIR = {
    "kind": "route_pair",
    "point": "checkpoint-1",
    "doc": "annotation",
    "slot": "supervisor",
    "persona": "supervisor",
    "present": True,
}
SIGNED_ANNOTATION = "signatures: [author, supervisor]"
UNSIGNED_ANNOTATION = "signatures: [author]"


@pytest.fixture
async def service(stand: Stand, monkeypatch: pytest.MonkeyPatch) -> PackOutcomeService:
    """Служба результата с зафиксированным днём: сценарии и результат считаются на одну дату."""
    assert stand.container is not None
    found = await stand.container.get(PackOutcomeService)
    monkeypatch.setattr(found, "_today", lambda: TODAY)
    return found


@pytest.fixture
async def scenarios(stand: Stand) -> PackScenarioService:
    assert stand.container is not None
    return await stand.container.get(PackScenarioService)


async def _put(stand: Stand, ws: str, scenario_id: str, body: dict[str, Any], **kw: Any) -> Any:
    return await put_scenario(stand, ws, VKR_TEMPLATE, scenario_id, body, **kw)


async def _file(stand: Stand, ws: str, scenario_id: str, template: tuple[str, str] = VKR_TEMPLATE) -> bytes:
    resp = await stand.read(ws, scenario_path(template, scenario_id))
    assert resp.status_code == 200, resp.text
    return resp.content


# ── список и запись ──────────────────────────────────────────────────────────


async def test__list__template_without_scenarios__empty_list_with_the_folder(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    listed = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE))

    assert listed.scenarios == []
    assert (listed.workspace_id, listed.pack, listed.template) == (ws, "hse-cs-se", "vkr")
    assert listed.dir == "hse-cs-se/templates/vkr/scenarios"


async def test__put__creates_the_canonical_file_and_the_file_endpoint_returns_the_same_bytes(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    body = scenario_body(
        "Научрук из компании",
        COMPANY,
        description={"ru": "Описание"},
        versions=["2026.1.*"],
        assertions=[{"kind": "participant_present", "persona": "co_supervisor", "present": True}],
    )

    resp = await _put(stand, ws, "company-supervisor", body)

    entry = parse_entry(resp)
    assert entry.id == "company-supervisor"
    assert entry.path == scenario_path(VKR_TEMPLATE, "company-supervisor")
    assert entry.error is None
    assert entry.scenario is not None
    assert entry.scenario.inputs == COMPANY
    assert resp.headers["ETag"] == entry.etag
    on_disk = (stand.root / "packs" / entry.path).read_bytes()
    assert on_disk == await _file(stand, ws, "company-supervisor")
    assert on_disk.decode("utf-8") == scenario_text(parse_scenario(on_disk.decode("utf-8")))
    assert on_disk.startswith("format: 1\nname:\n  ru: Научрук из компании\n".encode())
    # Ответ и список видят то же самое, ETag это ETag файла.
    listed = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE))
    assert [(e.id, e.etag) for e in listed.scenarios] == [("company-supervisor", entry.etag)]
    assert listed.scenarios[0].scenario == entry.scenario
    file_etag = (await stand.read(ws, entry.path)).headers["ETag"]
    assert file_etag == entry.etag


async def test__put__round_trip__writing_the_file_back_with_if_match_changes_nothing(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    first = parse_entry(await _put(stand, ws, "round-trip", scenario_body("Круг", COMPANY)))
    before = await _file(stand, ws, "round-trip")

    again = await _put(
        stand, ws, "round-trip", {"scenario": first.scenario.model_dump(mode="json")}, if_match=first.etag
    )

    assert parse_entry(again).etag == first.etag
    assert await _file(stand, ws, "round-trip") == before


async def test__put__edit_with_if_match__replaces_the_file_and_the_etag(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    first = parse_entry(await _put(stand, ws, "edit-me", scenario_body("Старое", COMPANY)))

    edited = parse_entry(
        await _put(stand, ws, "edit-me", scenario_body("Новое", {"supervisor": "none"}), if_match=first.etag)
    )

    assert edited.etag != first.etag
    assert edited.scenario is not None
    assert edited.scenario.name == {"ru": "Новое"}
    assert edited.scenario.inputs == {"supervisor": "none"}
    assert (await stand.read(ws, edited.path)).headers["ETag"] == edited.etag


async def test__put__existing_scenario_without_if_match__409_scenario_taken_and_the_file_is_kept(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    await _put(stand, ws, "taken", scenario_body("Первый", COMPANY))
    before = await _file(stand, ws, "taken")

    resp = await _put(stand, ws, "taken", scenario_body("Второй"))

    assert resp.status_code == 409
    assert resp.json()["code"] == "scenario_taken"
    assert await _file(stand, ws, "taken") == before


async def test__put__stale_if_match__409_stale_file_with_the_current_etag_and_text(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    first = parse_entry(await _put(stand, ws, "stale", scenario_body("Первый", COMPANY)))
    second = parse_entry(await _put(stand, ws, "stale", scenario_body("Второй"), if_match=first.etag))
    before = await _file(stand, ws, "stale")

    resp = await _put(stand, ws, "stale", scenario_body("Третий"), if_match=first.etag)

    assert resp.status_code == 409
    assert resp.json()["code"] == "stale_file"
    assert resp.json()["etag"] == second.etag
    assert resp.json()["content"] == before.decode("utf-8")
    assert await _file(stand, ws, "stale") == before


async def test__put__if_match_on_a_missing_scenario__404_scenario_not_found_and_nothing_is_created(
    stand: Stand,
) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await _put(stand, ws, "never-was", scenario_body("Нет"), if_match='"sha256-0"')

    assert resp.status_code == 404
    assert resp.json()["code"] == "scenario_not_found"
    assert not (stand.root / "packs" / scenario_path(VKR_TEMPLATE, "never-was")).exists()


@pytest.mark.parametrize(
    ("scenario_id", "body", "reason"),
    [
        ("Bad_Id", scenario_body("А"), "id: "),
        ("a--b", scenario_body("А"), "id: "),
        ("x" * 65, scenario_body("А"), "id: "),
        ("blank-name", scenario_body("  "), "name.ru: a non-empty string"),
        ("bad-lang", {"scenario": {"format": 1, "name": {"RU": "А"}, "inputs": {}}}, "name: language key"),
        ("empty-value", scenario_body("А", {"supervisor": ""}), "inputs.supervisor: a non-empty string"),
        ("bad-version", scenario_body("А", versions=["2026 1"]), "versions[0]: a quoted pattern"),
        (
            "blank-doc",
            scenario_body("А", assertions=[{"kind": "document_state", "doc": " ", "state": "active"}]),
            "assertions[0].doc: a non-empty string",
        ),
    ],
)
async def test__put__invalid_scenario__400_scenario_invalid_with_the_reason_and_no_file(
    stand: Stand, scenario_id: str, body: dict[str, Any], reason: str
) -> None:
    ws = await folder_with_real_packs(stand)
    before = tree_digest(stand.root / "packs")

    resp = await _put(stand, ws, scenario_id, body)

    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == "scenario_invalid"
    assert reason in resp.json()["reason"]
    assert tree_digest(stand.root / "packs") == before


@pytest.mark.parametrize(
    "scenario",
    [
        {"format": 1, "name": {}, "inputs": {}},
        {"format": 2, "name": {"ru": "А"}, "inputs": {}},
        {"format": 1, "name": {"ru": "А"}, "inputs": {}, "extra": 1},
        {"format": 1, "name": {"ru": "А"}, "inputs": {}, "assertions": [{"kind": "nope"}]},
        {"format": 1, "name": {"ru": "А"}, "inputs": {}, "assertions": [{"kind": "document_state", "doc": "a"}]},
    ],
    ids=["empty-name", "format-2", "extra-key", "unknown-kind", "missing-field"],
)
async def test__put__shape_errors__are_refused_by_the_strict_request_model(
    stand: Stand, scenario: dict[str, Any]
) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await _put(stand, ws, "shape", {"scenario": scenario})

    assert resp.status_code == 422
    assert not (stand.root / "packs" / scenario_path(VKR_TEMPLATE, "shape")).exists()


async def test__put__unknown_template_or_pack__404_and_no_folder_is_created(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    before = tree_digest(stand.root / "packs")

    ghost = await put_scenario(stand, ws, ("hse-cs-se", "ghost"), "a", scenario_body("А"))
    ghost_pack = await put_scenario(stand, ws, ("ghost", "vkr"), "a", scenario_body("А"))

    for resp in (ghost, ghost_pack):
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "version_not_found"
    assert tree_digest(stand.root / "packs") == before
    assert not (stand.root / "packs" / "ghost").exists()
    assert not (stand.root / "packs" / "hse-cs-se" / "templates" / "ghost").exists()


async def test__put__into_a_template_with_released_versions__writes_outside_the_version_directory(
    stand: Stand,
) -> None:
    ws = await folder_with_real_packs(stand)
    version_dir = stand.root / "packs" / "hse-cs-se" / "templates" / "vkr" / "versions" / "2026.1.2"
    released_before = tree_digest(version_dir)

    resp = await _put(stand, ws, "released-ok", scenario_body("Выпущенная версия", COMPANY, versions=["2026.1.2"]))

    assert resp.status_code == 200, resp.text
    # Дайджест выпущенной версии не меняется: сценарий лежит рядом с `examples/`, а не внутри каталога версии.
    assert tree_digest(version_dir) == released_before
    registry = (stand.root / "packs" / "hse-cs-se" / "templates" / "vkr" / "releases.yaml").read_text("utf-8")
    assert "2026.1.2" in registry


async def test__put__scenarios_folder_is_a_symlink__refused_and_nothing_is_written_outside(
    stand: Stand, tmp_path: Path
) -> None:
    ws = await folder_with_real_packs(stand)
    outside = tmp_path / "outside"
    outside.mkdir()
    (stand.root / "packs" / "hse-cs-se" / "templates" / "vkr" / "scenarios").symlink_to(outside)

    resp = await _put(stand, ws, "escape", scenario_body("Побег"))
    listed = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE))

    assert resp.status_code in (400, 403), resp.text
    assert resp.json()["code"] == "path_not_allowed"
    assert list(outside.iterdir()) == []
    assert listed.scenarios == []


async def test__put__too_many_scenarios__the_201st_is_refused(stand: Stand, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = await folder_with_real_packs(stand)
    monkeypatch.setattr(scenario_service, "MAX_SCENARIOS", 3)
    for n in range(3):
        assert (await _put(stand, ws, f"s{n}", scenario_body(f"С{n}"))).status_code == 200

    refused = await _put(stand, ws, "s3", scenario_body("С3"))
    edited = await _put(
        stand,
        ws,
        "s0",
        scenario_body("Правка"),
        if_match=parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE)).scenarios[0].etag,
    )

    assert refused.status_code == 400
    assert refused.json()["code"] == "scenario_invalid"
    assert "too many scenarios" in refused.json()["reason"]
    assert edited.status_code == 200, "правка существующего лимит не затрагивает"


# ── список с битыми файлами ──────────────────────────────────────────────────


async def test__list__broken_files_are_visible_with_the_error_and_foreign_files_are_ignored(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    await _put(stand, ws, "good", scenario_body("Хороший", COMPANY))
    folder = scenario_path(VKR_TEMPLATE, "x").rsplit("/", 1)[0]
    raw = {
        "broken-yaml.yaml": "name: [unclosed\n",
        "wrong-format.yaml": "format: 7\nname: { ru: А }\n",
        "unknown-key.yaml": "format: 1\nname: { ru: А }\nextra: 1\n",
        "Upper.yaml": "format: 1\nname: { ru: А }\n",
        "notes.md": "# заметки\n",
        "legacy.yml": "format: 1\nname: { ru: А }\n",
    }
    for name, text in raw.items():
        written = await stand.client.put(stand.file_url(ws, f"{folder}/{name}"), content=text.encode())
        assert written.status_code == 200, written.text
    binary = await stand.client.put(stand.file_url(ws, f"{folder}/binary.yaml"), content=b"\xff\xfe\x00\x01")
    assert binary.status_code == 200

    listed = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE))

    by_id = {e.id: e for e in listed.scenarios}
    assert sorted(by_id) == ["Upper", "binary", "broken-yaml", "good", "unknown-key", "wrong-format"]
    assert by_id["good"].error is None
    assert by_id["good"].scenario is not None
    assert "yaml: not a valid YAML document" in (by_id["broken-yaml"].error or "")
    assert "format: only 1" in (by_id["wrong-format"].error or "")
    assert "extra: unknown key" in (by_id["unknown-key"].error or "")
    assert (by_id["binary"].error or "").startswith(("the file is not UTF-8", "yaml:"))
    assert (by_id["Upper"].error or "").startswith("id: ")
    for entry in listed.scenarios:
        assert entry.etag
        assert entry.path == scenario_path(VKR_TEMPLATE, entry.id)
        assert (entry.scenario is None) == (entry.error is not None)


# ── удаление ─────────────────────────────────────────────────────────────────


async def test__delete__removes_the_file_and_put_without_if_match_brings_the_same_bytes_back(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    entry = parse_entry(await _put(stand, ws, "undo-me", scenario_body("Отмена", COMPANY, versions=["2026.1.*"])))
    before = await _file(stand, ws, "undo-me")

    deleted = await stand.client.delete(scenarios_url(ws, VKR_TEMPLATE, "/undo-me"), headers={"If-Match": entry.etag})
    gone = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE))
    assert deleted.status_code == 204
    assert gone.scenarios == []
    assert not (stand.root / "packs" / entry.path).exists()
    restored = await _put(stand, ws, "undo-me", {"scenario": entry.scenario.model_dump(mode="json")})
    assert parse_entry(restored).etag == entry.etag
    assert await _file(stand, ws, "undo-me") == before


async def test__delete__missing_scenario__404_scenario_not_found(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await stand.client.delete(scenarios_url(ws, VKR_TEMPLATE, "/ghost"))
    bad_id = await stand.client.delete(scenarios_url(ws, VKR_TEMPLATE, "/Bad_Id"))

    assert (resp.status_code, resp.json()["code"]) == (404, "scenario_not_found")
    assert (bad_id.status_code, bad_id.json()["code"]) == (400, "scenario_invalid")


async def test__delete__stale_if_match__409_and_the_file_stays(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    first = parse_entry(await _put(stand, ws, "keep-me", scenario_body("Один")))
    await _put(stand, ws, "keep-me", scenario_body("Два"), if_match=first.etag)

    resp = await stand.client.delete(scenarios_url(ws, VKR_TEMPLATE, "/keep-me"), headers={"If-Match": first.etag})

    assert (resp.status_code, resp.json()["code"]) == (409, "stale_file")
    assert (stand.root / "packs" / first.path).is_file()


async def test__delete__a_folder_named_like_a_scenario_is_not_deleted(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    trap = stand.root / "packs" / scenario_path(VKR_TEMPLATE, "trap")
    (trap / "inner").mkdir(parents=True)
    (trap / "inner" / "keep.txt").write_text("keep", encoding="utf-8")

    resp = await stand.client.delete(scenarios_url(ws, VKR_TEMPLATE, "/trap"))

    assert (resp.status_code, resp.json()["code"]) == (404, "scenario_not_found")
    assert (trap / "inner" / "keep.txt").is_file()


# ── подстановка вводных сценария в результат ─────────────────────────────────


async def test__outcome__scenario_inputs_lie_between_the_defaults_and_the_request_inputs(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    await _put(
        stand,
        ws,
        "company",
        scenario_body("Компания", {"kind": "research", "supervisor": "company", "co_supervisor": "yes"}),
    )

    plain = parse_outcome(await post_outcome(stand, ws, VKR))
    scenario = parse_outcome(await post_outcome(stand, ws, VKR, {"scenario": "company"}))
    over = parse_outcome(await post_outcome(stand, ws, VKR, {"scenario": "company", "inputs": {"supervisor": "none"}}))

    assert (plain.inputs["kind"], plain.inputs["supervisor"], plain.inputs["co_supervisor"]) == (
        "project",
        "university",
        "no",
    )
    assert (scenario.inputs["kind"], scenario.inputs["supervisor"], scenario.inputs["co_supervisor"]) == (
        "research",
        "company",
        "yes",
    )
    # Вводная запроса сильнее сценария, остальное от сценария.
    assert (over.inputs["supervisor"], over.inputs["co_supervisor"], over.inputs["kind"]) == ("none", "yes", "research")
    other = parse_outcome(await post_outcome(stand, ws, VKR, {"inputs": scenario.inputs}))
    assert scenario.fingerprint == other.fingerprint
    assert dict(scenario.inputs.items()) == other.inputs


async def test__outcome__scenario_without_example_uses_the_auto_normal_set_and_the_request_example_wins(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    await _put(stand, ws, "plain", scenario_body("Обычный"))
    await _put(stand, ws, "long", scenario_body("Длинный", example="auto:long"))

    plain = parse_outcome(await post_outcome(stand, ws, VKR, {"scenario": "plain"}))
    long = parse_outcome(await post_outcome(stand, ws, VKR, {"scenario": "long"}))
    forced = parse_outcome(await post_outcome(stand, ws, VKR, {"scenario": "long", "example": "auto:empty"}))

    assert (plain.example, long.example, forced.example) == ("auto:normal", "auto:long", "auto:empty")


async def test__outcome__unknown_scenario__404_scenario_not_found(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)

    unknown = await post_outcome(stand, ws, VKR, {"scenario": "ghost"})
    bad_id = await post_outcome(stand, ws, VKR, {"scenario": "Bad Id"})

    for resp in (unknown, bad_id):
        assert (resp.status_code, resp.json()["code"]) == (404, "scenario_not_found")


async def test__outcome__broken_scenario_file__400_scenario_invalid_with_the_reason(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    folder = scenario_path(VKR_TEMPLATE, "x").rsplit("/", 1)[0]
    await stand.client.put(stand.file_url(ws, f"{folder}/broken.yaml"), content=b"format: 1\nname: { ru: A }\nzzz: 1\n")

    resp = await post_outcome(stand, ws, VKR, {"scenario": "broken"})

    assert (resp.status_code, resp.json()["code"]) == (400, "scenario_invalid")
    assert resp.json()["reason"] == "zzz: unknown key"
    assert resp.json()["scenario"] == "broken"


async def test__outcome__scenario_input_that_does_not_fit_the_version__400_inputs_invalid(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    await _put(stand, ws, "stale-input", scenario_body("Устарела", {"supervisor": "martian"}))
    await _put(stand, ws, "gone-input", scenario_body("Нет такой", {"meta.gone": "yes"}))

    martian = await post_outcome(stand, ws, VKR, {"scenario": "stale-input"})
    gone = await post_outcome(stand, ws, VKR, {"scenario": "gone-input"})

    assert (martian.status_code, martian.json()["code"], martian.json()["field"]) == (
        400,
        "inputs_invalid",
        "supervisor",
    )
    assert (gone.status_code, gone.json()["code"], gone.json()["field"]) == (400, "inputs_invalid", "meta.gone")


async def test__outcome__etag_follows_the_scenario_file_and_gives_304_when_nothing_changed(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    entry = parse_entry(await _put(stand, ws, "etag", scenario_body("Имя", COMPANY)))
    first = await post_outcome(stand, ws, VKR, {"scenario": "etag"})
    etag = first.headers["ETag"]

    same = await post_outcome(stand, ws, VKR, {"scenario": "etag"}, **{"If-None-Match": etag})
    # Правка, которая не меняет вводных (только имя), всё равно меняет ключ: ответ привязан к файлу сценария.
    await _put(stand, ws, "etag", scenario_body("Другое имя", COMPANY), if_match=entry.etag)
    renamed = await post_outcome(stand, ws, VKR, {"scenario": "etag"}, **{"If-None-Match": etag})
    changed = await _put(
        stand,
        ws,
        "etag",
        scenario_body("Другое имя", {"supervisor": "none"}),
        if_match=parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE)).scenarios[0].etag,
    )
    after = await post_outcome(stand, ws, VKR, {"scenario": "etag"}, **{"If-None-Match": etag})

    assert same.status_code == 304
    assert renamed.status_code == 200
    assert renamed.headers["ETag"] != etag
    assert changed.status_code == 200
    assert after.status_code == 200
    assert parse_outcome(after).inputs["supervisor"] == "none"
    # Без сценария ключ от сценариев не зависит.
    bare = await post_outcome(stand, ws, VKR)
    await _put(stand, ws, "other", scenario_body("Другой"))
    assert (await post_outcome(stand, ws, VKR, **{"If-None-Match": bare.headers["ETag"]})).status_code == 304


async def test__inputs__scenario_selects_its_example_and_an_unknown_scenario_is_404(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    await _put(stand, ws, "long", scenario_body("Длинный", example="auto:long"))

    plain = await stand.client.get(outcome_url(ws, VKR, "/inputs"))
    scenario = await stand.client.get(outcome_url(ws, VKR, "/inputs"), params={"scenario": "long"})
    unknown = await stand.client.get(outcome_url(ws, VKR, "/inputs"), params={"scenario": "ghost"})
    bare = await get_inputs(stand, ws, VKR)

    assert scenario.status_code == 200
    assert scenario.headers["ETag"] != plain.headers["ETag"]
    assert plain.json()["inputs"] == scenario.json()["inputs"]
    assert (unknown.status_code, unknown.json()["code"]) == (404, "scenario_not_found")
    assert bare.headers["ETag"] == plain.headers["ETag"]


# ── прогон ───────────────────────────────────────────────────────────────────


async def _seed(stand: Stand, ws: str) -> dict[str, str]:
    """Сценарии разных статусов на ВКР. Возвращает ETag файлов по id."""
    etags: dict[str, str] = {}

    async def put(scenario_id: str, body: dict[str, Any]) -> None:
        etags[scenario_id] = parse_entry(await _put(stand, ws, scenario_id, body)).etag

    await put(
        "passes",
        scenario_body(
            "Проходит",
            {"kind": "research", **COMPANY},
            versions=["2026.1.*"],
            assertions=[
                {"kind": "participant_present", "persona": "co_supervisor", "present": True},
                {"kind": "document_state", "doc": "annotation", "state": "active"},
            ],
        ),
    )
    await put(
        "fails",
        scenario_body(
            "Падает",
            {"kind": "research"},
            assertions=[
                {"kind": "participant_present", "persona": "co_supervisor", "present": True},
                {"kind": "participant_present", "persona": "supervisor", "present": True},
            ],
        ),
    )
    await put("stale-input", scenario_body("Устарела", {"supervisor": "martian"}))
    await put("no-expectation", scenario_body("Без ожидания", {"kind": "research"}))
    await put("old-versions", scenario_body("Старые версии", {"kind": "research"}, versions=["2025.*"]))
    folder = scenario_path(VKR_TEMPLATE, "x").rsplit("/", 1)[0]
    await stand.client.put(
        stand.file_url(ws, f"{folder}/broken-file.yaml"), content=b"format: 1\nname: { ru: A }\nzzz: 1\n"
    )
    return etags


async def test__run__all_scenarios__statuses_counters_messages_and_the_strict_model(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    await _seed(stand, ws)

    resp = await run_scenarios(stand, ws, VKR_TEMPLATE)

    run = parse_run(resp)
    assert (run.workspace_id, run.pack, run.template, run.version, run.state) == (
        ws,
        "hse-cs-se",
        "vkr",
        "2026.1.2",
        "work_tree",
    )
    assert run.revision.startswith("sha256-")
    got = {r.scenario: r for r in run.results}
    assert [r.scenario for r in run.results] == sorted(got), "по порядку id"
    assert {k: v.status for k, v in got.items()} == {
        "broken-file": "error",
        "fails": "failed",
        "no-expectation": "unchecked",
        "old-versions": "unchecked",
        "passes": "passed",
        "stale-input": "error",
    }
    assert (run.passed, run.failed, run.errors, run.unchecked) == (1, 1, 2, 2)
    assert got["broken-file"].message == "zzz: unknown key"
    assert (got["stale-input"].message or "").startswith("supervisor='martian'")
    assert got["old-versions"].message == "version 2026.1.2 is outside versions: 2025.*"
    assert got["no-expectation"].message is None
    assert got["no-expectation"].fingerprint
    assert got["passes"].failures == []
    (failure,) = got["fails"].failures
    assert (failure.index, failure.kind, failure.expected, failure.actual) == (
        0,
        "participant_present",
        "true",
        "false",
    )
    assert run.coverage.scenarios == 6
    assert run.coverage.rules_total > 0
    assert resp.headers["Cache-Control"] == "private, no-cache"


async def test__run__result_fingerprint_equals_the_outcome_of_the_scenario(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    await _seed(stand, ws)

    run = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE))

    outcome = parse_outcome(await post_outcome(stand, ws, VKR, {"scenario": "passes"}))
    assert next(r for r in run.results if r.scenario == "passes").fingerprint == outcome.fingerprint


async def test__run__selected_scenarios_only__and_unknown_id_is_404(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)
    await _seed(stand, ws)

    one = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"scenarios": ["passes"]}))
    two = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"scenarios": ["fails", "passes", "fails"]}))
    ghost = await run_scenarios(stand, ws, VKR_TEMPLATE, {"scenarios": ["passes", "ghost"]})
    empty = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"scenarios": []}))

    assert [r.scenario for r in one.results] == ["passes"]
    assert [r.scenario for r in two.results] == ["fails", "passes"]
    assert (ghost.status_code, ghost.json()["code"], ghost.json()["scenario"]) == (404, "scenario_not_found", "ghost")
    assert empty.results == []
    assert empty.coverage.scenarios == 0


async def test__run__template_without_scenarios__empty_run_not_an_error(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)

    run = parse_run(await run_scenarios(stand, ws, COURSEWORK_TEMPLATE))

    assert (run.passed, run.failed, run.errors, run.unchecked, run.results) == (0, 0, 0, 0, [])
    assert run.version == "2026.1.6"


async def test__run__unknown_template__404_version_not_found(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await run_scenarios(stand, ws, ("hse-cs-se", "ghost"))

    assert (resp.status_code, resp.json()["code"]) == (404, "version_not_found")


async def test__run__version_choice__newest_by_number_by_default_and_the_named_one_on_request(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws, root = await folder_with_draft(stand)
    # Рядом с черновиком `2026.1.9` ложится выпущенная `2026.1.2` и её реестр.
    template = REAL_PACKS / "hse-cs-se" / "templates" / "vkr"
    target = root / "hse-cs-se" / "templates" / "vkr"
    shutil.copytree(template / "versions" / "2026.1.2", target / "versions" / "2026.1.2")
    shutil.copy(template / "releases.yaml", target / "releases.yaml")
    await _put(
        stand,
        ws,
        "everywhere",
        scenario_body(
            "Везде", COMPANY, assertions=[{"kind": "participant_present", "persona": "co_supervisor", "present": True}]
        ),
    )
    await _put(stand, ws, "only-old", scenario_body("Только старая", COMPANY, versions=["2026.1.2"]))
    await _put(stand, ws, "only-new", scenario_body("Только новая", COMPANY, versions=["2026.1.9"]))

    newest = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE))
    old = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE, {"version": "2026.1.2"}))
    ghost = await run_scenarios(stand, ws, VKR_TEMPLATE, {"version": "2099.1.1"})

    assert newest.version == "2026.1.9"
    assert {r.scenario: r.status for r in newest.results} == {
        "everywhere": "passed",
        "only-new": "unchecked",
        "only-old": "unchecked",
    }
    assert {r.scenario: (r.status, r.message) for r in newest.results}["only-old"] == (
        "unchecked",
        "version 2026.1.9 is outside versions: 2026.1.2",
    )
    assert old.version == "2026.1.2"
    assert {r.scenario: r.status for r in old.results}["only-old"] == "unchecked"  # нет ожидания
    assert {r.scenario: r.message for r in old.results}["only-new"] == "version 2026.1.2 is outside versions: 2026.1.9"
    assert (ghost.status_code, ghost.json()["code"]) == (404, "version_not_found")


async def test__run__etag_and_304__edit_of_a_scenario_or_a_manifest_changes_it(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws, _ = await folder_with_draft(stand)
    first_entry = parse_entry(await _put(stand, ws, "one", scenario_body("Один", {"kind": "research"})))
    first = await run_scenarios(stand, ws, VKR_TEMPLATE)
    etag = first.headers["ETag"]

    same = await run_scenarios(stand, ws, VKR_TEMPLATE, **{"If-None-Match": etag})
    await _put(stand, ws, "one", scenario_body("Один, переименован", {"kind": "research"}), if_match=first_entry.etag)
    renamed = await run_scenarios(stand, ws, VKR_TEMPLATE, **{"If-None-Match": etag})
    renamed_etag = renamed.headers["ETag"]
    await edit_manifest(stand, ws, SIGNED_ANNOTATION, UNSIGNED_ANNOTATION)
    edited = await run_scenarios(stand, ws, VKR_TEMPLATE, **{"If-None-Match": renamed_etag})
    one = await run_scenarios(stand, ws, VKR_TEMPLATE, {"scenarios": ["one"]}, **{"If-None-Match": renamed_etag})

    assert same.status_code == 304
    assert same.headers["ETag"] == etag
    assert renamed.status_code == 200
    assert renamed_etag != etag
    assert edited.status_code == 200
    assert edited.headers["ETag"] != renamed_etag
    assert one.status_code == 200, "выбор сценариев входит в ключ"


async def test__run__repeated_run_is_answered_from_the_cache_without_calculating(
    stand: Stand, service: PackOutcomeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    await _seed(stand, ws)
    calls = 0
    real = scenario_service.run_scenarios

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(scenario_service, "run_scenarios", counting)

    first = await run_scenarios(stand, ws, VKR_TEMPLATE)
    second = await run_scenarios(stand, ws, VKR_TEMPLATE)
    await _put(stand, ws, "extra", scenario_body("Ещё"))
    third = await run_scenarios(stand, ws, VKR_TEMPLATE)

    assert calls == 2
    assert first.json() == second.json()
    assert third.json() != first.json()


async def test__run__edit_of_the_manifest__failed_with_changes_and_the_snapshot_is_accepted_by_put(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws, _ = await folder_with_draft(stand)
    body = scenario_body(
        "Аннотация подписана",
        {"kind": "research"},
        versions=["2026.1.*"],
        assertions=[CHECKPOINT_PAIR],
        record_snapshot="work_tree",
    )
    created = parse_entry(await _put(stand, ws, "annotation-signed", body))
    assert created.scenario is not None
    snapshot = created.scenario.snapshot
    assert snapshot is not None
    # Снимок записан сервером из текущего результата и равен `digest` результата того же сценария.
    outcome = parse_outcome(await post_outcome(stand, ws, DRAFT_VKR, {"scenario": "annotation-signed"}))
    assert snapshot.model_dump(mode="json") == outcome.digest.model_dump(mode="json")
    before = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE))
    assert [r.status for r in before.results] == ["passed"]

    await edit_manifest(stand, ws, SIGNED_ANNOTATION, UNSIGNED_ANNOTATION)
    after = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE))

    (result,) = after.results
    assert result.status == "failed"
    assert [(f.index, f.kind) for f in result.failures] == [(0, "route_pair"), (None, "snapshot")]
    assert (result.failures[0].expected, result.failures[0].actual) == ("true", "false")
    assert result.failures[0].why
    changes = {(c.kind, c.id): c for c in result.changes}
    pairs = changes[("route_pair", "checkpoint-1/pairs")]
    assert (pairs.symbol, pairs.section) == ("~", "route")
    assert int(pairs.after or "0") == int(pairs.before or "0") - 1
    assert result.failures[1].expected == snapshot_fingerprint_of(snapshot.model_dump(mode="json"))
    assert result.failures[1].actual == result.fingerprint

    # «Принять текущий результат как ожидаемый»: снимок записывается заново по ETag файла; утверждение остаётся
    # прежним и теперь падает само, пока автор не поправит и его.
    accepted = parse_entry(
        await _put(
            stand,
            ws,
            "annotation-signed",
            {"scenario": created.scenario.model_dump(mode="json"), "record_snapshot": "work_tree"},
            if_match=created.etag,
        )
    )
    again = parse_run(await run_scenarios(stand, ws, VKR_TEMPLATE))

    assert accepted.scenario is not None
    assert accepted.scenario.snapshot != snapshot
    (rerun,) = again.results
    assert [(f.index, f.kind) for f in rerun.failures] == [(0, "route_pair")]
    assert rerun.changes == []


def snapshot_fingerprint_of(digest: dict[str, Any]) -> str:
    from hse_doc_studio.core.pack_studio.outcome.model import SectionPrint  # noqa: PLC0415 — только здесь
    from hse_doc_studio.core.pack_studio.outcome.summary import fingerprint_of  # noqa: PLC0415

    return fingerprint_of(tuple(SectionPrint(**section) for section in digest["sections"]))


async def test__put__record_snapshot__bad_scenario_for_the_version_is_scenario_invalid_and_nothing_is_written(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    before = tree_digest(stand.root / "packs")

    martian = await _put(
        stand, ws, "martian", scenario_body("Марс", {"supervisor": "martian"}, record_snapshot="work_tree")
    )
    no_version = await _put(
        stand, ws, "future", scenario_body("Будущее", versions=["2099.*"], record_snapshot="work_tree")
    )
    named_outside = await _put(
        stand,
        ws,
        "named",
        scenario_body("Не та", versions=["2026.1.*"], record_snapshot="work_tree", version="2099.1.1"),
    )
    no_example = await _put(
        stand, ws, "no-example", scenario_body("Набор", example="nope", record_snapshot="work_tree")
    )

    assert martian.status_code == 400
    assert martian.json()["reason"].startswith("supervisor='martian'")
    assert no_version.status_code == 404, no_version.text
    assert no_version.json()["code"] == "version_not_found"
    assert named_outside.status_code == 400
    assert "outside versions" in named_outside.json()["reason"]
    assert no_example.status_code == 400
    assert no_example.json()["reason"] == "example 'nope': unknown example"
    assert tree_digest(stand.root / "packs") == before


async def test__put__record_snapshot_without_a_snapshot_state_and_with_one__only_the_requested_one_is_recorded(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)

    plain = parse_entry(await _put(stand, ws, "no-snap", scenario_body("Без снимка", COMPANY)))
    snap = parse_entry(await _put(stand, ws, "snap", scenario_body("Со снимком", COMPANY, record_snapshot="work_tree")))

    assert plain.scenario is not None
    assert plain.scenario.snapshot is None
    assert snap.scenario is not None
    assert snap.scenario.snapshot is not None
    assert list(snap.scenario.snapshot.documents) == [
        d.id for d in parse_outcome(await post_outcome(stand, ws, VKR, {"scenario": "snap"})).documents
    ]
    # Снимок из тела запроса затирается снимком сервера (клиентский не доверяется).
    forged = scenario_body("Подделка", COMPANY, record_snapshot="work_tree")
    forged["scenario"]["snapshot"] = {
        "documents": {"ghost": "active"},
        "participants": [],
        "meta_visible": [],
        "points": [],
        "sections": [],
    }
    recorded = parse_entry(await _put(stand, ws, "forged", forged))
    assert recorded.scenario is not None
    assert recorded.scenario.snapshot is not None
    assert "ghost" not in recorded.scenario.snapshot.documents


# ---- git-состояния без git и пределы ----------------------------------------


async def test__run__head_and_base_without_git__diff_base_unavailable(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    await _seed(stand, ws)

    for state in ("head", "base"):
        run = await run_scenarios(stand, ws, VKR_TEMPLATE, {"state": state})
        listed = await list_scenarios(stand, ws, VKR_TEMPLATE, state)
        for resp in (run, listed):
            assert (resp.status_code, resp.json()["code"], resp.json()["reason"]) == (
                409,
                "diff_base_unavailable",
                "no_git",
            )


async def test__run__invalid_state_is_refused_by_the_request_model(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)

    resp = await run_scenarios(stand, ws, VKR_TEMPLATE, {"state": "yesterday"})

    assert resp.status_code == 422


@pytest.fixture
def slow_resolve(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Расчёт сценария, который долго держит поток; задержку можно обнулить, не снимая подмену."""
    delay = [0.6]
    real = scenario_runner.resolve

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(delay[0])
        return real(*args, **kwargs)

    monkeypatch.setattr(scenario_runner, "resolve", slow)
    return delay


async def test__run__over_the_time_limit__503_outcome_busy_and_nothing_is_cached(
    stand: Stand, service: PackOutcomeService, slow_resolve: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await folder_with_real_packs(stand)
    await _seed(stand, ws)
    await get_inputs(stand, ws, VKR)  # разбор версии в отдельном процессе не входит в предел расчёта
    monkeypatch.setattr(service, "_limits", replace(service._limits, timeout_s=0.1))
    started = time.perf_counter()

    resp = await run_scenarios(stand, ws, VKR_TEMPLATE)

    assert time.perf_counter() - started < slow_resolve[0]
    assert (resp.status_code, resp.json()["code"], resp.json()["reason"]) == (503, "outcome_busy", "timeout")
    assert resp.headers["Retry-After"] == "2"
    # Неудачный прогон в кэш не попал: после того как залипший поток закончил, тот же запрос проходит.
    slow_resolve[0] = 0.0
    monkeypatch.setattr(service, "_limits", replace(service._limits, timeout_s=30.0))
    await asyncio.sleep(0.6 * 12)
    assert (await run_scenarios(stand, ws, VKR_TEMPLATE)).status_code == 200


# ---- права, частота и отсутствие побочных эффектов ---------------------------


async def test__scenarios__section_turned_off__every_endpoint_is_refused_before_anything_is_read(stand: Stand) -> None:
    ws = await folder_with_real_packs(stand)
    await stand.client.put(f"{API}/section", json={"enabled": False})

    answers = [
        await list_scenarios(stand, ws, VKR_TEMPLATE),
        await _put(stand, ws, "a", scenario_body("А")),
        await stand.client.delete(scenarios_url(ws, VKR_TEMPLATE, "/a")),
        await run_scenarios(stand, ws, VKR_TEMPLATE),
    ]

    for resp in answers:
        assert resp.status_code == 404
        assert resp.json()["code"] == "pack_studio_disabled"
    assert not (stand.root / "packs" / "hse-cs-se" / "templates" / "vkr" / "scenarios").exists()


async def test__scenarios__unknown_workspace__404(stand: Stand) -> None:
    await stand.enable()
    ghost = "00000000-0000-4000-8000-000000000000"

    answers = [
        await list_scenarios(stand, ghost, VKR_TEMPLATE),
        await _put(stand, ghost, "a", scenario_body("А")),
        await run_scenarios(stand, ghost, VKR_TEMPLATE),
    ]

    for resp in answers:
        assert (resp.status_code, resp.json()["code"]) == (404, "workspace_not_found")


async def test__run__rate_limit__the_pack_outcome_rule_covers_the_run(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    app = stand.client._transport.app  # type: ignore[attr-defined]
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.rate_limit_scale = 1.0
    await run_scenarios(stand, ws, VKR_TEMPLATE)  # разбор версии не должен съесть секунду окна

    start = time.perf_counter()
    answers = [await run_scenarios(stand, ws, VKR_TEMPLATE) for _ in range(25)]

    if time.perf_counter() - start < 1.0:
        refused = [r for r in answers if r.status_code == 429]
        assert refused
        assert refused[0].headers["Retry-After"] == "1"
        assert refused[0].json()["code"] == "rate_limited"
    assert answers[0].status_code == 200


async def test__scenarios__reading_and_running_write_nothing_and_a_put_writes_only_the_scenario_file(
    stand: Stand, service: PackOutcomeService
) -> None:
    ws = await folder_with_real_packs(stand)
    packs = stand.root / "packs"
    pristine = tree_digest(packs)

    await list_scenarios(stand, ws, VKR_TEMPLATE)
    await run_scenarios(stand, ws, VKR_TEMPLATE)
    await post_outcome(stand, ws, VKR)
    await get_inputs(stand, ws, VKR)
    assert tree_digest(packs) == pristine

    await _put(stand, ws, "only-me", scenario_body("Единственный", COMPANY, record_snapshot="work_tree"))
    await run_scenarios(stand, ws, VKR_TEMPLATE)

    after = tree_digest(packs)
    assert set(after) - set(pristine) == {scenario_path(VKR_TEMPLATE, "only-me")}
    assert {k: v for k, v in after.items() if k in pristine} == pristine
    # Ничего вне папки паков: ни писем, ни подписей, ни сборок.
    assert sorted(p.name for p in stand.root.iterdir() if p.name != "packs" and p.name != "data") == []


async def test__scenarios__the_two_templates_do_not_see_each_other(stand: Stand, service: PackOutcomeService) -> None:
    ws = await folder_with_real_packs(stand)
    await _put(stand, ws, "vkr-only", scenario_body("ВКР", COMPANY))
    await put_scenario(
        stand, ws, COURSEWORK_TEMPLATE, "course-only", scenario_body("Курсовой", {"supervisor": "company"})
    )

    vkr = parse_list(await list_scenarios(stand, ws, VKR_TEMPLATE))
    course = parse_list(await list_scenarios(stand, ws, COURSEWORK_TEMPLATE))
    course_run = parse_run(await run_scenarios(stand, ws, COURSEWORK_TEMPLATE))
    cross = await post_outcome(stand, ws, COURSEWORK, {"scenario": "vkr-only"})

    assert [e.id for e in vkr.scenarios] == ["vkr-only"]
    assert [e.id for e in course.scenarios] == ["course-only"]
    assert [r.scenario for r in course_run.results] == ["course-only"]
    assert (cross.status_code, cross.json()["code"]) == (404, "scenario_not_found")
