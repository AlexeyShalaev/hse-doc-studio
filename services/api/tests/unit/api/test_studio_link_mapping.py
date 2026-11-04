"""Ответ связи с облаком: состояние проекта на Студии не тащит служебных ключей отчёта."""

from __future__ import annotations

from hse_doc_studio.api.routers.v1.studio_link import _project


def test__project__service_key_of_the_report_is_not_part_of_the_response() -> None:
    report = {
        "project_id": "11111111-1111-1111-1111-111111111111",
        "sync": "ahead",
        "ahead": 2,
        "behind": 0,
        "last_sync_at": "2026-11-03T12:00:00+00:00",
        "auto_sync": True,
        "pdf": {"doc_id": "vkr", "at": "2026-11-03T12:01:00+00:00", "ok": False, "code": "pdf_too_large"},
    }

    shown = _project(report)

    assert shown is not None
    assert (shown.sync, shown.ahead, shown.auto_sync) == ("ahead", 2, True)
    assert shown.pdf is not None
    assert (shown.pdf.doc_id, shown.pdf.ok, shown.pdf.code) == ("vkr", False, "pdf_too_large")


def test__project__no_report_means_no_state() -> None:
    assert _project(None) is None
