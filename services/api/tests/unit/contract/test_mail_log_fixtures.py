"""Эталоны журнала писем (docs/design/mail-log.md, 6.2) согласованы с правилами строки журнала.

Форму эталонов проверяет `test_server_contract.py`; здесь смысл: итог и причина, сбой только у `failed`, Message-ID
только у `sent`, вид удалён без превью, сводка со сбоем в окне. Эталоны лежат в `contracts/server/pending`, пока у
них нет zod-схем фронтенда, затем в `contracts/server/fixtures`: тест читает тот каталог, где они есть.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.mail.journal import (
    ERROR_TEXT_MAX,
    REASONS_BY_STATUS,
    SUBJECT_MAX,
    MailCause,
    MailOrigin,
    MailRefKind,
    MailStatus,
    known_template,
)
from hse_doc_studio.core.mail.samples import _TOKEN as SAMPLE_TOKEN

_CONTRACT = Path(__file__).resolve().parents[5] / "contracts" / "server"
_SCHEMAS = ("AdminMailLogEntry", "AdminMailLogPage", "AdminMailLogDetail", "AdminMailLogSummary")


def _dir(schema: str) -> Path:
    found = [root / schema for root in (_CONTRACT / "fixtures", _CONTRACT / "pending") if (root / schema).is_dir()]
    assert len(found) == 1, schema
    return found[0]


def _bodies(schema: str) -> dict[str, Any]:
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(_dir(schema).glob("*.json"))}


def _entries() -> list[tuple[str, dict[str, Any]]]:
    out = [(f"entry/{name}", body) for name, body in _bodies("AdminMailLogEntry").items()]
    for name, body in _bodies("AdminMailLogPage").items():
        out += [(f"page/{name}/{item['id']}", item) for item in body["items"]]
    out += [(f"detail/{name}", body["entry"]) for name, body in _bodies("AdminMailLogDetail").items()]
    return out


_ENTRIES = _entries()


@pytest.mark.parametrize(("label", "entry"), _ENTRIES, ids=[label for label, _ in _ENTRIES])
def test_entry_follows_the_row_rules(label: str, entry: dict[str, Any]) -> None:
    status = MailStatus(entry["status"])
    if status is MailStatus.sent:
        assert entry["reason"] is None
    else:
        assert entry["reason"] in REASONS_BY_STATUS[status]
    assert (entry["failure"] is not None) == (status is MailStatus.failed)
    assert (entry["message_id"] is not None) == (status is MailStatus.sent)
    if entry["failure"] and entry["failure"]["text"]:
        assert len(entry["failure"]["text"]) <= ERROR_TEXT_MAX
        assert "\n" not in entry["failure"]["text"]
    assert entry["template_known"] == (known_template(entry["template"]) is not None)
    assert entry["origin"] in set(MailOrigin)
    cause = MailCause(entry["cause"])
    assert (entry["task"] is not None) == (cause is MailCause.system)
    if cause is not MailCause.user:
        assert entry["actor"] is None
    if entry["ref"] is not None:
        assert entry["ref"]["kind"] in set(MailRefKind)
    assert len(entry["subject"]) <= SUBJECT_MAX


def test_entries_cover_every_status_and_cause() -> None:
    entries = _bodies("AdminMailLogEntry").values()
    assert {e["status"] for e in entries} == set(MailStatus)
    assert {e["cause"] for e in entries} == set(MailCause)


def test_pages_are_newest_first() -> None:
    for body in _bodies("AdminMailLogPage").values():
        ids = [item["id"] for item in body["items"]]
        assert ids == sorted(ids, reverse=True)


def test_detail_preview_matches_its_flags() -> None:
    for name, body in _bodies("AdminMailLogDetail").items():
        assert (body["preview"] is None) == (not body["entry"]["template_known"]), name
        if body["link_hidden"]:
            assert "[ссылка скрыта]" in body["preview"]["text"] or "[link hidden]" in body["preview"]["text"], name
        if body["note_hidden"]:
            assert "не хранится в журнале" in body["preview"]["text"], name


def test_summary_has_a_last_failure_only_with_failures() -> None:
    for name, body in _bodies("AdminMailLogSummary").items():
        assert (body["last_failure"] is not None) == (body["failed"] > 0), name
        assert body["smtp_configured"] or body["sent"] == 0, name


def test_fixtures_carry_no_links_with_tokens() -> None:
    for schema in _SCHEMAS:
        for name, body in _bodies(schema).items():
            dumped = json.dumps(body, ensure_ascii=False)
            assert SAMPLE_TOKEN not in dumped, (schema, name)
            assert "href=" not in dumped, (schema, name)
