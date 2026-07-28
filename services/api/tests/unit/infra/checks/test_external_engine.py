from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.external_engine import ExternalCheckEngine

from tests.factories import make_check_rule


class _FakeManager:
    """Stand-in for LanguageToolContainerManager — only `current_base_url` is read."""

    def __init__(self, base_url: str | None) -> None:
        self.current_base_url = base_url


def _engine(base_url: str | None, handler: Any) -> ExternalCheckEngine:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ExternalCheckEngine(container_manager=_FakeManager(base_url), client=client)


def _rule(**params: Any):
    return make_check_rule(rule_id="hse-pi-lang/languagetool", engine=CheckEngine.external, params=params)


# ── gating: no live container → no HTTP, no results ────────────────────────


@pytest.mark.unit
def test__external_engine__no_base_url__returns_empty_and_makes_no_request(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text("текст", encoding="utf-8")
    called = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"matches": []})

    results = _engine(None, handler).run(_rule(), CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)

    assert results == []
    assert called["n"] == 0


# ── mapping: matches -> CheckResult with lt: id, resolved severity, location ─


@pytest.mark.unit
def test__external_engine__maps_matches_to_results(tmp_path: Path) -> None:
    content = "Первая строка.\nВторая строка с ашибкой здесь.\nТретья."
    (tmp_path / "main.tex").write_text(content, encoding="utf-8")
    offset = content.index("ашибкой")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Возможная орфографическая ошибка.",
                        "offset": offset,
                        "length": 7,
                        "rule": {"id": "MORFOLOGIK_RULE_RU_RU"},
                    }
                ]
            },
        )

    results = _engine("http://127.0.0.1:8010", handler).run(
        _rule(), CheckSeverity.err, tmp_path, "doc1", "main.tex", None
    )

    assert len(results) == 1
    res = results[0]
    assert res.rule_id == "lt:MORFOLOGIK_RULE_RU_RU"
    assert res.severity == CheckSeverity.err  # rule's resolved severity, not hardcoded warn
    assert res.message == "Возможная орфографическая ошибка."
    assert res.location is not None
    assert res.location.file == "main.tex"
    assert res.location.line == 2


@pytest.mark.unit
def test__external_engine__unknown_rule_id__falls_back_to_unknown(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text("текст", encoding="utf-8")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"matches": [{"message": "x", "offset": 0}]})

    results = _engine("http://127.0.0.1:8010", handler).run(
        _rule(), CheckSeverity.warn, tmp_path, "doc1", "main.tex", None
    )

    assert results[0].rule_id == "lt:UNKNOWN"
    assert results[0].location.line == 1


# ── request shape ──────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("base_url", ["http://127.0.0.1:49160", "http://127.0.0.1:49160/"])
def test__external_engine__posts_to_v2_check(tmp_path: Path, base_url: str) -> None:
    (tmp_path / "main.tex").write_text("текст", encoding="utf-8")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"matches": []})

    _engine(base_url, handler).run(_rule(language="ru-RU"), CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)

    assert captured["url"] == "http://127.0.0.1:49160/v2/check"
    form = parse_qs(captured["body"])
    assert form["language"] == ["ru-RU"]
    assert form["disabledRules"] == ["WHITESPACE_RULE,DoubleNOT,PREP_C_and_Noun,UPPERCASE_SENTENCE_START"]


@pytest.mark.unit
def test__external_engine__auto_language__preferred_variants_sent(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text("text", encoding="utf-8")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"matches": []})

    rule = _rule(language="auto", preferred_variants="en-GB")
    _engine("http://127.0.0.1:49160", handler).run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)

    assert parse_qs(captured["body"])["preferredVariants"] == ["en-GB"]


@pytest.mark.unit
def test__external_engine__explicit_language__preferred_variants_omitted(tmp_path: Path) -> None:
    # LanguageTool отвечает 400 на пару «явный язык + preferredVariants»,
    # поэтому вариант уезжает только вместе с автоопределением.
    (tmp_path / "main.tex").write_text("text", encoding="utf-8")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"matches": []})

    rule = _rule(language="en-US", preferred_variants="en-GB")
    _engine("http://127.0.0.1:49160", handler).run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)

    assert "preferredVariants" not in parse_qs(captured["body"])


# ── robustness: never raise ─────────────────────────────────────────────────


def _http_500(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, text="boom")


def _connect_error(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused")


@pytest.mark.unit
@pytest.mark.parametrize("handler", [_http_500, _connect_error])
def test__external_engine__request_fails__returns_empty(tmp_path: Path, handler: Any) -> None:
    (tmp_path / "main.tex").write_text("текст", encoding="utf-8")

    results = _engine("http://127.0.0.1:8010", handler).run(
        _rule(), CheckSeverity.warn, tmp_path, "doc1", "main.tex", None
    )

    assert results == []


@pytest.mark.unit
def test__external_engine__source_file_missing__returns_empty(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        return httpx.Response(200, json={"matches": []})

    results = _engine("http://127.0.0.1:8010", handler).run(
        _rule(), CheckSeverity.warn, tmp_path, "doc1", "missing.tex", None
    )
    assert results == []


@pytest.mark.unit
def test__external_engine__resolves_source_in_doc_subdir(tmp_path: Path) -> None:
    (tmp_path / "vkr").mkdir()
    (tmp_path / "vkr" / "vkr.tex").write_text("слово\nс ашибкой", encoding="utf-8")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"matches": [{"message": "m", "offset": 6, "rule": {"id": "R"}}]})

    results = _engine("http://127.0.0.1:8010", handler).run(
        _rule(), CheckSeverity.warn, tmp_path, "vkr", "vkr/vkr.tex", None
    )

    assert len(results) == 1
    assert results[0].location.file in ("vkr/vkr.tex", str(Path("vkr/vkr.tex")))
    assert results[0].location.line == 2
