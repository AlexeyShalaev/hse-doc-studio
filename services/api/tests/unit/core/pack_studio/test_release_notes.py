"""Черновик заметок к версии из отчёта классификатора (template-studio.md, 7.4; срез T10)."""

from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.pack_studio.release_notes import draft_notes
from hse_doc_studio.core.template_diff import (
    ChangeReason,
    ChangeReport,
    VersionSnapshot,
    classify_snapshots,
    load_snapshot,
)

_PATCH = TemplateUpdateClass.patch
_MINOR = TemplateUpdateClass.minor
_REPO = Path(__file__).resolve().parents[6]


def _snapshot(manifest: dict, documents: dict | None = None) -> VersionSnapshot:
    return VersionSnapshot(
        version_id="2026.1.1",
        manifest=manifest,
        roster=tuple(documents or ()),
        documents=documents or {},
        checks={},
        files={},
    )


def _reason(code: str, path: str, cls: TemplateUpdateClass = _PATCH) -> ChangeReason:
    return ChangeReason(code=code, path=path, change="added", minimum=cls, suggested=cls, hard=True)


def test_items_are_parallel_and_name_entities_by_their_labels() -> None:
    new = _snapshot(
        {
            "meta_fields": {"title_en": {"label": {"ru": "Название на английском", "en": "Title in English"}}},
            "signatures": {"slots": [{"id": "supervisor", "label": {"ru": "Руководитель", "en": "Supervisor"}}]},
        },
        {"report": {"name": {"ru": "Отчёт", "en": "Report"}}},
    )
    report = ChangeReport(
        "2026.1",
        "2026.1.1",
        (
            _reason("signing_preset", "signatures.slots[supervisor].placements"),
            _reason("signing_preset", "signatures.slots[supervisor].default_dates"),
            _reason("field_added", "meta_fields.title_en", _MINOR),
            _reason("file_changed", "files/report/main.tex"),
            _reason("file_changed", "files/common/meta.tex.j2"),
        ),
    )

    notes = draft_notes(report, new)

    assert notes.changes["ru"] == (
        "Новые поля: «Название на английском».",
        "Места подписей и метки даты заданы шаблоном: «Руководитель».",
        "Исправлены файлы документов: «Отчёт», общие файлы.",
    )
    assert notes.changes["en"][0] == 'New fields: "Title in English".'
    assert len(notes.changes["ru"]) == len(notes.changes["en"])
    assert notes.breaking_changes == {"ru": (), "en": ()}


def test_narrowing_is_proposed_for_breaking_changes_with_names_from_the_base() -> None:
    base = _snapshot({"meta_fields": {"city": {"label": {"ru": "Город", "en": "City"}}}})
    report = ChangeReport("2026.1", "2026.2.0", (_reason("removed", "meta_fields.city", _MINOR),))

    notes = draft_notes(report, _snapshot({}), base)

    assert notes.breaking_changes["ru"] == ("Удалено: «Город».",)
    assert notes.changes["en"] == ('Removed: "City".',)


def test_texts_without_an_entity_get_a_plain_item() -> None:
    report = ChangeReport("2026.1", "2026.1.1", (_reason("text", "summary_hint"),))

    notes = draft_notes(report, _snapshot({}))

    assert notes.changes == {"ru": ("Уточнены тексты интерфейса.",), "en": ("Interface texts are refined.",)}


def test_real_pack_patch_lists_the_refined_labels() -> None:
    versions = _REPO / "packs/hse-cs-sse/templates/coursework/versions"
    base, new = load_snapshot(versions / "2026.1.5"), load_snapshot(versions / "2026.1.6")

    notes = draft_notes(classify_snapshots(base, new), new, base)

    assert len(notes.changes["ru"]) == 1
    assert "«Моноширинный шрифт (код, листинги)»" in notes.changes["ru"][0]
