"""Метаданные устройства: очистка имени и кодов, окно присутствия (docs/design/connected-devices.md, раздел 4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.devices.entities import (
    PresenceConfig,
    clean_text,
    os_of,
    sanitize_code,
    sanitize_doc_id,
    sanitize_endpoint_name,
    sanitize_model,
    sanitize_name,
)

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MacBook Алексея", "MacBook Алексея"),
        ("  MacBook \t Pro \n", "MacBook Pro"),
        ("Bell\x00\x07\x1b[31mred", "Bell[31mred"),
        ("/Users/ivan/Documents/project", ""),
        ("C:\\Users\\ivan\\proj", ""),
        ("~/work", ""),
        ("моя /home/ivan", ""),
        ("x" * 200, "x" * 64),
    ],
)
def test__sanitize_name__removes_controls_and_rejects_paths(raw: str, expected: str) -> None:
    assert sanitize_name(raw) == expected


def test__clean_text__keeps_ordinary_text_and_cuts_by_limit() -> None:
    assert clean_text("a" * 10, 4) == "aaaa"
    assert clean_text("ёжик", 10) == "ёжик"


@pytest.mark.parametrize(("raw", "expected"), [("ollama", "ollama"), ("Ollama", "ollama"), ("../x", None), ("", None)])
def test__sanitize_endpoint_name__only_slug(raw: str, expected: str | None) -> None:
    assert sanitize_endpoint_name(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), [("pdf_failed", "pdf_failed"), ("/etc/passwd", None), (None, None)])
def test__sanitize_code__only_code_like(raw: str | None, expected: str | None) -> None:
    assert sanitize_code(raw) == expected


def test__sanitize_doc_id__rejects_path_fragments() -> None:
    assert sanitize_doc_id("vkr--shalaev") == "vkr--shalaev"
    assert sanitize_doc_id("../vkr") is None


@pytest.mark.parametrize(("raw", "ok"), [("qwen3:4b-instruct", True), ("/Users/x/models/q.gguf", False), ("", False)])
def test__sanitize_model__name_without_path(raw: str, ok: bool) -> None:
    assert (sanitize_model(raw) is not None) is ok


def test__os_of__unknown_value_falls_back_to_other() -> None:
    assert os_of("macos").value == "macos"
    assert os_of("plan9").value == "other"
    assert os_of(None).value == "other"


def test__presence_online__window_is_inclusive_and_configurable() -> None:
    config = PresenceConfig(online_window_s=180)

    assert config.online(NOW - timedelta(seconds=180), NOW)
    assert not config.online(NOW - timedelta(seconds=181), NOW)
