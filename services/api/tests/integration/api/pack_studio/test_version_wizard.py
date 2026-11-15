"""Студия шаблонов, срез T10: мастер «Новая версия» (template-studio.md, раздел 7, 4.3 и 4.5).

Пространство над папкой (выпущенные по реестру на диске) и над git (выпущенные по реестру базовой ветки, голый
репозиторий по file://). Копия, живой класс, номер, заметки, перенос правок выпущенной версии и выпуск.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from hse_doc_studio.infra.template.releases import freeze, load_releases, version_digest

from tests.fixtures.git_remote import seed_remote
from tests.integration.api.pack_studio.conftest import (
    API,
    DRAFT,
    DRAFT_DIR,
    PACK_FILES,
    RELEASED,
    RELEASED_DIR,
    TEMPLATE_DIR,
    Stand,
    write_pack,
)
from tests.integration.api.pack_studio.test_git_workspace import _git_workspace, _remote, _store

_PACK = "demo"
_TEMPLATE = "report"
_VERSIONS = f"{API}/workspaces/{{ws}}/templates/{_PACK}/{_TEMPLATE}/versions"
_CITY = '  city:\n    type: string\n    label: { ru: "Город", en: "City" }\n'
_FIELD = '  title_en:\n    type: string\n    label: { ru: "Название на английском", en: "Title in English" }\n'
# Пак с полем анкеты в обеих версиях: новое поле черновика это причина `field_added`, а не новый блок.
_FILES = {
    rel: text + ("meta_fields:\n" + _CITY if rel.endswith("version.yaml") else "") for rel, text in PACK_FILES.items()
}


def _version_url(ws_id: str, version: str, tail: str) -> str:
    return f"{API}/workspaces/{ws_id}/versions/{_PACK}/{_TEMPLATE}/{version}/{tail}"


async def _folder(stand: Stand) -> tuple[str, Path]:
    folder = write_pack(stand.root / "packs-folder", _FILES)
    await stand.enable()
    ws = await stand.folder_workspace(folder)
    return str(ws["id"]), folder


async def _state(stand: Stand, ws_id: str, version: str) -> dict[str, Any]:
    resp = await stand.client.get(_version_url(ws_id, version, "state"))
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _manifest(folder: Path, version: str) -> dict[str, Any]:
    text = (folder / TEMPLATE_DIR / "versions" / version / "version.yaml").read_text(encoding="utf-8")
    return dict(yaml.safe_load(text))


def _add_field(folder: Path, version: str) -> None:
    path = folder / TEMPLATE_DIR / "versions" / version / "version.yaml"
    path.write_text(path.read_text(encoding="utf-8") + _FIELD, encoding="utf-8")


# ── папка ───────────────────────────────────────────────────────────────────


async def test__options__default_base_is_the_last_released_and_numbers_follow_the_latest(stand: Stand) -> None:
    ws_id, _ = await _folder(stand)

    resp = await stand.client.get(_VERSIONS.format(ws=ws_id))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["default_base"] == RELEASED
    assert body["default_version"] == RELEASED
    assert body["numbers"] == {"patch": "2026.1.2", "minor": "2026.2.0", "major": "2027.1"}
    assert [(v["version"], v["released"], v["status"]) for v in body["versions"]] == [
        (RELEASED, True, "stable"),
        (DRAFT, False, "beta"),
    ]


async def test__create__copies_the_base_into_a_beta_draft(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)

    resp = await stand.client.post(_VERSIONS.format(ws=ws_id), json={"update_class": "minor"})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["version"] == {
        "pack": _PACK,
        "template": _TEMPLATE,
        "version": "2026.2.0",
        "path": f"{TEMPLATE_DIR}/versions/2026.2.0",
    }
    assert body["base"] == RELEASED
    manifest = _manifest(folder, "2026.2.0")
    assert manifest["id"] == "2026.2.0"
    assert manifest["status"] == "beta"
    copied = folder / TEMPLATE_DIR / "versions/2026.2.0/files/report/main.tex"
    assert copied.read_bytes() == (folder / RELEASED_DIR / "files/report/main.tex").read_bytes()
    # Комментарий и выравнивание манифеста базы остались: правка точечная.
    assert "# Демо-версия для тестов Студии шаблонов." in copied.parent.parent.parent.joinpath(
        "version.yaml"
    ).read_text(encoding="utf-8")


async def test__create__taken_number__suggests_the_next_free(stand: Stand) -> None:
    ws_id, _ = await _folder(stand)

    resp = await stand.client.post(_VERSIONS.format(ws=ws_id), json={"version": DRAFT})

    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "version_taken"
    assert resp.json()["suggested"] == "2026.1.2"


async def test__state__live_class_follows_edits(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)

    patch = await _state(stand, ws_id, DRAFT)
    _add_field(folder, DRAFT)
    minor = await _state(stand, ws_id, DRAFT)

    assert patch["base"] == RELEASED
    assert (patch["minimum"], patch["suggested"], patch["by_number"]) == ("patch", "patch", "patch")
    assert patch["number_ok"] is True
    assert [r["code"] for r in patch["reasons"]] == ["file_changed"]
    assert patch["headline"]["ru"].startswith("patch:")
    assert len(patch["draft_changes"]["ru"]) == len(patch["draft_changes"]["en"]) == 1
    assert minor["minimum"] == "minor"
    assert minor["number_ok"] is False
    assert minor["numbers"] == {"patch": DRAFT, "minor": "2026.2.0", "major": "2027.1"}
    assert "«Название на английском»" in minor["draft_changes"]["ru"][0]
    assert '"Title in English"' in minor["draft_changes"]["en"][0]


async def test__renumber__not_softer_than_the_minimum_and_moves_the_folder(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)
    _add_field(folder, DRAFT)

    softer = await stand.client.post(_version_url(ws_id, DRAFT, "renumber"), json={"version": "2026.1.5"})
    moved = await stand.client.post(_version_url(ws_id, DRAFT, "renumber"), json={"version": "2026.2.0"})

    assert softer.status_code == 409, softer.text
    assert softer.json()["code"] == "class_softer_than_changes"
    assert softer.json()["minimum"] == "minor"
    assert moved.status_code == 200, moved.text
    assert moved.json()["version"]["version"] == "2026.2.0"
    assert moved.json()["previous"] == DRAFT
    assert not (folder / DRAFT_DIR).exists()
    assert _manifest(folder, "2026.2.0")["id"] == "2026.2.0"
    assert (await _state(stand, ws_id, "2026.2.0"))["number_ok"] is True


async def test__notes__written_as_block_lists_and_the_note_explains_the_class(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)

    resp = await stand.client.put(
        _version_url(ws_id, DRAFT, "notes"),
        json={
            "changes": {"ru": ["Исправлен титул: «Отчёт»."], "en": ["The title page is fixed."]},
            "note": "Файл шаблона меняет только комментарий.",
        },
    )
    cleared = await stand.client.put(_version_url(ws_id, DRAFT, "notes"), json={"note": ""})

    assert resp.status_code == 200, resp.text
    assert resp.json()["changes"] == {"ru": ["Исправлен титул: «Отчёт»."], "en": ["The title page is fixed."]}
    assert resp.json()["note"] == "Файл шаблона меняет только комментарий."
    text = (folder / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8")
    assert "changes:\n  ru:\n    - " in text
    assert cleared.json()["note"] is None
    assert "release" not in _manifest(folder, DRAFT)


async def test__release__folder__freezes_marks_stable_and_sets_the_default(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)
    await stand.client.put(
        _version_url(ws_id, DRAFT, "notes"),
        json={"changes": {"ru": ["Правка титула."], "en": ["Title page fix."]}},
    )

    resp = await stand.client.post(_version_url(ws_id, DRAFT, "release"), json={"set_default": True})
    write = await stand.client.put(stand.file_url(ws_id, f"{DRAFT_DIR}/files/report/main.tex"), content=b"late\n")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "patch"
    assert body["previous"] == RELEASED
    assert body["default_set"] is True
    entries = load_releases(folder / TEMPLATE_DIR)
    assert entries[DRAFT].digest == body["digest"] == version_digest(folder / DRAFT_DIR)
    manifest = _manifest(folder, DRAFT)
    assert manifest["status"] == "stable"
    assert manifest["release"] == {"kind": "patch"}
    template = yaml.safe_load((folder / TEMPLATE_DIR / "template.yaml").read_text(encoding="utf-8"))
    assert template["default_version"] == DRAFT
    # У папки выпуск сразу окончательный: реестр на диске и есть база.
    assert write.status_code == 409
    assert write.json()["code"] == "version_released"
    assert (await _state(stand, ws_id, DRAFT))["released"] is True


async def test__release__lint_errors__nothing_changes(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)
    await stand.client.put(_version_url(ws_id, DRAFT, "notes"), json={"changes": {"ru": ["Только ru"], "en": []}})
    before = (folder / DRAFT_DIR / "version.yaml").read_bytes()

    resp = await stand.client.post(_version_url(ws_id, DRAFT, "release"), json={})

    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "lint_failed"
    assert resp.json()["findings"]
    assert (folder / DRAFT_DIR / "version.yaml").read_bytes() == before
    assert DRAFT not in load_releases(folder / TEMPLATE_DIR)


async def test__release__kind_softer_than_the_changes__is_refused(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)
    _add_field(folder, DRAFT)

    resp = await stand.client.post(_version_url(ws_id, DRAFT, "release"), json={"kind": "patch"})

    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "class_softer_than_changes"


async def test__move_edits__folder__released_version_edited_outside__copies_into_a_draft(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)
    (folder / RELEASED_DIR / "files/report/main.tex").write_text("tampered\n", encoding="utf-8")

    state = await _state(stand, ws_id, RELEASED)
    resp = await stand.client.post(_version_url(ws_id, RELEASED, "move-edits"), json={})
    clean = await stand.client.post(_version_url(ws_id, DRAFT, "move-edits"), json={})

    assert state["released"] is True
    assert state["modified"] is True
    assert state["move_to"] == "2026.1.2"
    assert resp.status_code == 200, resp.text
    assert resp.json()["version"]["version"] == "2026.1.2"
    assert resp.json()["restored"] is False
    moved = folder / TEMPLATE_DIR / "versions/2026.1.2"
    assert (moved / "files/report/main.tex").read_text(encoding="utf-8") == "tampered\n"
    assert _manifest(folder, "2026.1.2")["status"] == "beta"
    assert clean.status_code == 409
    assert clean.json()["code"] == "version_not_modified"


async def test__released_version__notes_and_renumber_are_refused(stand: Stand) -> None:
    ws_id, _ = await _folder(stand)

    notes = await stand.client.put(_version_url(ws_id, RELEASED, "notes"), json={"note": "x"})
    renumber = await stand.client.post(_version_url(ws_id, RELEASED, "renumber"), json={"version": "2026.3.0"})

    assert notes.status_code == 409
    assert notes.json()["code"] == "version_released"
    assert renumber.json()["code"] == "version_released"


async def test__unknown_template__is_not_found(stand: Stand) -> None:
    ws_id, _ = await _folder(stand)

    resp = await stand.client.get(f"{API}/workspaces/{ws_id}/templates/{_PACK}/nope/versions")

    assert resp.status_code == 404
    assert resp.json()["code"] == "version_not_found"


# ── git ─────────────────────────────────────────────────────────────────────

_PROFILE = {"name": "Анна Иванова", "email": "anna@example.org"}


async def _git_ready(stand: Stand) -> tuple[Any, str, Path]:
    remote = _remote(stand.root)
    resp = await stand.client.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    ws = await _git_workspace(stand, remote)
    assert ws["state"] == "ready", ws
    ws_id = str(ws["id"])
    return remote, ws_id, _store(stand, ws_id) / "tree" / "packs"


def _their_release(stand: Stand, version: str) -> dict[str, str | bytes]:
    """Чужой выпуск `version` в базовой ветке: каталог и запись реестра, как их сделал бы `pack freeze`."""
    stage = write_pack(stand.root / "their-stage")
    target = stage / TEMPLATE_DIR / "versions" / version
    target.mkdir(parents=True)
    (target / "files/report").mkdir(parents=True)
    (target / "files/report/main.tex").write_text("\\documentclass{article}\n% theirs\n", encoding="utf-8")
    (target / "version.yaml").write_text(
        f'id: "{version}"\nstatus: stable\nsummary: {{ ru: "Чужая", en: "Theirs" }}\nlangs: [ru]\n', encoding="utf-8"
    )
    freeze(stage / TEMPLATE_DIR, version)
    files: dict[str, str | bytes] = {
        f"packs/{path.relative_to(stage).as_posix()}": path.read_bytes() for path in target.rglob("*") if path.is_file()
    }
    files[f"packs/{TEMPLATE_DIR}/releases.yaml"] = (stage / TEMPLATE_DIR / "releases.yaml").read_bytes()
    return files


async def test__git_release__is_a_branch_edit_until_merged_and_can_be_repeated(stand: Stand) -> None:
    _, ws_id, tree = await _git_ready(stand)
    created = await stand.client.post(_VERSIONS.format(ws=ws_id), json={})
    version = created.json()["version"]["version"]

    first = await stand.client.post(_version_url(ws_id, version, "release"), json={})
    (tree / TEMPLATE_DIR / "versions" / version / "files/report/main.tex").write_text("after\n", encoding="utf-8")
    outdated = await _state(stand, ws_id, version)
    again = await stand.client.post(_version_url(ws_id, version, "release"), json={})
    git = (await stand.client.get(f"{API}/workspaces/{ws_id}/git")).json()

    assert created.status_code == 201, created.text
    assert version == "2026.1.2"
    assert first.status_code == 200, first.text
    assert first.json()["replaced"] is False
    assert outdated["released"] is False
    assert outdated["registered"] is True
    assert outdated["release_outdated"] is True
    assert again.status_code == 200, again.text
    assert again.json()["replaced"] is True
    assert load_releases(tree / TEMPLATE_DIR)[version].digest == version_digest(
        tree / TEMPLATE_DIR / "versions" / version
    )
    assert git["dirty"] is True


async def test__git_number_taken_in_base__release_refused_then_edits_move_and_base_merges_cleanly(
    stand: Stand,
) -> None:
    remote, ws_id, tree = await _git_ready(stand)
    created = await stand.client.post(_VERSIONS.format(ws=ws_id), json={})
    version = created.json()["version"]["version"]
    mine = tree / TEMPLATE_DIR / "versions" / version / "files/report/main.tex"
    mine.write_text("\\documentclass{article}\n% mine\n", encoding="utf-8")
    await stand.client.put(
        _version_url(ws_id, version, "notes"), json={"changes": {"ru": ["Моя правка."], "en": ["My fix."]}}
    )
    commit = await stand.client.post(f"{API}/workspaces/{ws_id}/git/commit", json={})
    assert commit.status_code == 200, commit.text
    seed_remote(remote, _their_release(stand, version), message="their release")

    refused = await stand.client.post(_version_url(ws_id, version, "release"), json={})
    state = await _state(stand, ws_id, version)
    moved = await stand.client.post(_version_url(ws_id, version, "move-edits"), json={"version": state["move_to"]})
    await stand.client.post(f"{API}/workspaces/{ws_id}/git/commit", json={"message": "move"})
    merged = await stand.client.post(f"{API}/workspaces/{ws_id}/git/merge-base")

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "version_taken"
    assert refused.json()["released_in_base"] is True
    assert refused.json()["suggested"] == "2026.1.3"
    assert state["released"] is True
    assert state["modified"] is True
    assert moved.status_code == 200, moved.text
    assert moved.json()["restored"] is True
    new_dir = tree / TEMPLATE_DIR / "versions/2026.1.3"
    assert (new_dir / "files/report/main.tex").read_text(encoding="utf-8").endswith("% mine\n")
    # Свои заметки переехали вместе с правками: это черновик автора, а не чужой выпуск.
    assert yaml.safe_load((new_dir / "version.yaml").read_text(encoding="utf-8"))["changes"]["en"] == ["My fix."]
    assert (
        (tree / TEMPLATE_DIR / "versions" / version / "files/report/main.tex")
        .read_text(encoding="utf-8")
        .endswith("% theirs\n")
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["behind"] == 0
    assert (await _state(stand, ws_id, version))["modified"] is False


async def test__git_move_edits__released_version_tampered_on_disk__is_restored_from_the_base(stand: Stand) -> None:
    _, ws_id, tree = await _git_ready(stand)
    released_dir = tree / RELEASED_DIR
    digest = version_digest(released_dir)
    (released_dir / "files/report/main.tex").write_text("tampered\n", encoding="utf-8")
    (released_dir / "files/report/extra.tex").write_text("extra\n", encoding="utf-8")

    resp = await stand.client.post(_version_url(ws_id, RELEASED, "move-edits"), json={})

    assert resp.status_code == 200, resp.text
    assert resp.json()["restored"] is True
    assert resp.json()["version"]["version"] == "2026.1.2"
    assert version_digest(released_dir) == digest
    assert not (released_dir / "files/report/extra.tex").exists()
    moved = tree / TEMPLATE_DIR / "versions/2026.1.2/files/report"
    assert (moved / "main.tex").read_text(encoding="utf-8") == "tampered\n"
    assert (moved / "extra.tex").is_file()
