"""Слова интерфейса в ответах MCP Студии шаблонов (pack-studio-mcp.md, P3): тексты совпадают со строками интерфейса,
находки линтера результата получают те же заголовки и «Как исправить», что вкладка «Проверка»."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.use_cases.mcp.tools import pack_plain
from hse_doc_studio.use_cases.mcp.tools.pack_plain import Naming, lint_plain_text, next_step_label, plain_finding

_SERVICES = Path(__file__).resolve().parents[5]
_LOCALES = _SERVICES / "web-app" / "src" / "shared" / "lib" / "i18n" / "locales"
_FIXTURES = _SERVICES.parent / "contracts" / "pack-studio" / "fixtures"
_WEB_RULES = _SERVICES / "web-app" / "src" / "features" / "pack-space" / "plain" / "findings.ts"


@pytest.fixture(autouse=True)
def _lang() -> Iterator[None]:
    set_interface_language("ru")
    yield
    set_interface_language(None)


def _locale(lang: str, name: str) -> dict[str, Any]:
    return dict(json.loads((_LOCALES / lang / "packSpace" / f"{name}.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("lang", ["ru", "en"])
def test__texts__are_the_interface_strings(lang: str) -> None:
    ours = pack_plain.texts(lang)
    plain = _locale(lang, "plain")
    check = _locale(lang, "check")
    changes = _locale(lang, "changes")
    situation = _locale(lang, "situation")

    for key, value in ours["plain"].items():
        assert value == plain[key], key
    for key, value in ours["issues"].items():
        assert value == check["issues"][key], key
    assert ours["next"] == changes["next"]
    for key, value in ours["situation"].items():
        assert value == situation[key], key


def test__rules__match_the_interface_list() -> None:
    source = _WEB_RULES.read_text(encoding="utf-8")
    block = source.split("export const LINT_RULES = [", 1)[1].split("]", 1)[0]
    web = {part.strip().strip('"') for part in block.split(",") if part.strip()}
    assert web == set(pack_plain.LINT_RULES)


def _naming() -> Naming:
    return Naming(
        lang="ru",
        documents={"project_proposal": {"ru": "Проектное предложение"}, "report": {"ru": "Отчёт"}},
        slots={"academic_supervisor": {"ru": "Академический руководитель"}},
        points={"defense": {"ru": "Защита"}},
    )


def test__plain_finding__title_and_how_from_the_rule() -> None:
    finding = {
        "rule_id": "when-never-held",
        "severity": "warning",
        "message": "Условие when слота «academic_supervisor» документа «project_proposal» в «defense» не выполнено.",
        "pointer": "/signing_slots/1/when",
    }

    plain = plain_finding(finding, _naming())

    assert plain["known"] is True
    assert plain["title"] == (
        "Подпись «Академический руководитель» у документа «Проектное предложение» в «Защита» не появится никогда"
    )
    assert plain["how"].startswith("Проверьте, о каком человеке говорит условие")


def test__plain_finding__unknown_rule_keeps_the_server_text() -> None:
    plain = plain_finding({"rule_id": "new-rule", "message": "Текст", "hint": "Совет"}, _naming())
    assert plain == {"title": "Текст", "how": "Совет", "extra": None, "known": False}


def test__lint_text__fixture_reads_like_the_check_tab() -> None:
    body = json.loads((_FIXTURES / "PackOutcomeLint" / "coursework.json").read_text(encoding="utf-8"))

    text, truncated = lint_plain_text(body, _naming(), ("error", "warning", "info"), "info", 40)

    assert text.startswith(f"Проверка шаблона. Ошибок: {body['errors']}, замечаний: {body['warnings']}")
    assert "Как исправить:" in text
    assert "Правил проверено готовыми случаями:" in text
    assert "{{" not in text
    assert truncated is False
    for finding in body["findings"]:
        assert "{{" not in plain_finding(finding, _naming())["title"]


def test__next_step_label__english_and_request_checks() -> None:
    assert next_step_label("fixErrors", {"count": 2}, "en") == "Fix errors · 2"
    assert next_step_label("request", {"label": "#4", "checks": "passed"}, "ru") == "Запрос #4 · проверки прошли"
    assert next_step_label("request", {"label": "#4", "checks": "unknown"}, "ru") == "Запрос #4 открыт"
