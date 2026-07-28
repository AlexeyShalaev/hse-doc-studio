from __future__ import annotations

from pathlib import Path

from hse_doc_studio.use_cases.chat.start_chat_turn import _read_rules


def test__read_rules__rules_file_present__returns_its_text(tmp_path: Path) -> None:
    rules_path = tmp_path / ".hse-studio" / "agent" / "rules.md"
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text("Всегда соблюдай ГОСТ 7.32.", encoding="utf-8")

    assert _read_rules(tmp_path) == "Всегда соблюдай ГОСТ 7.32."


def test__read_rules__rules_file_absent_or_blank__returns_none(tmp_path: Path) -> None:
    assert _read_rules(tmp_path) is None

    empty = tmp_path / ".hse-studio" / "agent" / "rules.md"
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_text("   \n", encoding="utf-8")

    assert _read_rules(tmp_path) is None
