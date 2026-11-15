"""Шаги мастера «Новая версия» поверх функций CLI паков (template-studio.md, 7.1, 7.3, 4.3; срез T10)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.infra.pack_studio.versions import (
    PackVersionError,
    copy_version,
    create_version,
    free_number,
    previous_version,
    release_version,
    renumber_version,
    restore_registry,
)
from hse_doc_studio.infra.pack_studio.yaml_edits import set_value
from hse_doc_studio.infra.template.releases import ReleaseEntry, load_releases

from tests.unit.infra.pack_studio.test_pack_cli import _fill_notes, _template

_DAY = date(2026, 11, 15)


def _manifest(template: Path, version: str) -> dict:
    return yaml.safe_load((template / "versions" / version / "version.yaml").read_text(encoding="utf-8"))


def test_free_number_skips_numbers_taken_in_the_base() -> None:
    assert free_number("2026.1.3", TemplateUpdateClass.patch, ["2026.1.4", "2026.1.5"]) == "2026.1.6"
    assert free_number("2026.1.3", TemplateUpdateClass.minor, ["2026.2.0"]) == "2026.2.1"
    assert free_number("2026.1", TemplateUpdateClass.major, []) == "2027.1"


def test_create_version_counts_numbers_taken_outside_the_tree(tmp_path: Path) -> None:
    template = _template(tmp_path)

    created = create_version(template, taken=["2026.1.1"], today=_DAY)

    assert created.version == "2026.1.2"
    assert created.base == "2026.1"


def test_create_version_refuses_a_number_taken_in_the_base(tmp_path: Path) -> None:
    template = _template(tmp_path)

    with pytest.raises(PackVersionError, match="уже есть"):
        create_version(template, to="2026.1.1", taken=["2026.1.1"])


def test_renumber_moves_the_draft_and_drops_its_branch_release(tmp_path: Path) -> None:
    template = _template(tmp_path)
    create_version(template, today=_DAY)
    _fill_notes(template / "versions" / "2026.1.1")
    release_version(template, "2026.1.1", mark_released=True, set_default=True, today=_DAY)

    moved = renumber_version(template, "2026.1.1", "2026.2.0", today=_DAY)

    assert moved.unreleased is True
    assert not (template / "versions" / "2026.1.1").exists()
    manifest = _manifest(template, "2026.2.0")
    assert (manifest["id"], manifest["status"]) == ("2026.2.0", "beta")
    assert manifest["changes"]["en"] == ["Fix."]
    assert "2026.1.1" not in load_releases(template)
    assert "2026.2.0" not in load_releases(template)
    template_yaml = yaml.safe_load((template / "template.yaml").read_text(encoding="utf-8"))
    assert template_yaml["default_version"] == "2026.2.0"


def test_renumber_refuses_taken_and_lower_numbers(tmp_path: Path) -> None:
    template = _template(tmp_path)
    create_version(template, today=_DAY)

    with pytest.raises(PackVersionError, match="уже есть"):
        renumber_version(template, "2026.1.1", "2026.1.2", taken=["2026.1.2"])
    with pytest.raises(PackVersionError, match="выше базы"):
        renumber_version(template, "2026.1.1", "2025.9.0")
    assert (template / "versions" / "2026.1.1").is_dir()


def test_copy_version_keeps_notes_only_when_asked(tmp_path: Path) -> None:
    template = _template(tmp_path)

    copy_version(template, "2026.1", "2026.1.1", keep_notes=True, today=_DAY)
    copy_version(template, "2026.1", "2026.1.2", keep_notes=False, today=_DAY)

    kept, emptied = _manifest(template, "2026.1.1"), _manifest(template, "2026.1.2")
    assert kept["changes"]["ru"] == ["Первая версия."]
    assert kept["release"] == {"kind": "major"}
    assert kept["status"] == emptied["status"] == "beta"
    assert emptied["changes"]["ru"] == []
    assert "release" not in emptied


def test_restore_registry_takes_base_entries_and_keeps_own_drafts(tmp_path: Path) -> None:
    template = _template(tmp_path)
    create_version(template, today=_DAY)
    _fill_notes(template / "versions" / "2026.1.1")
    release_version(template, "2026.1.1", mark_released=True, today=_DAY)
    base = {
        "2026.1": load_releases(template)["2026.1"],
        "2026.1.2": ReleaseEntry("2026.1.2", "sha256:theirs", TemplateUpdateClass.patch),
    }

    changed = restore_registry(template, base)
    again = restore_registry(template, base)

    assert changed is True
    assert again is False
    assert set(load_releases(template)) == {"2026.1", "2026.1.1", "2026.1.2"}
    assert load_releases(template)["2026.1.2"].digest == "sha256:theirs"


def test_previous_version_prefers_released(tmp_path: Path) -> None:
    template = _template(tmp_path)
    create_version(template, today=_DAY)
    create_version(template, today=_DAY)

    assert previous_version(template, "2026.1.2") == "2026.1"
    assert previous_version(template, "2026.1") is None


def test_set_value_block_writes_new_lists_as_items() -> None:
    text = "id: 1\nchanges:\n  ru: []\n  en: []\n"

    edited = set_value(text, ("changes", "ru"), ["Пункт: один", "Два"], block=True)
    flow = set_value(text, ("changes", "ru"), ["Два"])

    assert edited == "id: 1\nchanges:\n  ru:\n    - 'Пункт: один'\n    - Два\n  en: []\n"
    assert flow == "id: 1\nchanges:\n  ru: [Два]\n  en: []\n"
