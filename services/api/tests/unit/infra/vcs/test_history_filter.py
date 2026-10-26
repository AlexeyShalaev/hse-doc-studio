from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hse_doc_studio.core.vcs.entities import VcsHistoryQuery
from hse_doc_studio.infra.vcs.history_filter import ere_escape, git_args, kind_matches, matches, needs_python, raw_kind

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("v1.2", r"v1\.2"),
        ("(a|b)*", r"\(a\|b\)\*"),
        ("[x]{2}^$", r"\[x\]\{2\}\^\$"),
        ("back\\slash", "back\\\\slash"),
        ("plain слово", "plain слово"),
    ],
)
def test__ere_escape__makes_the_text_literal(raw: str, expected: str) -> None:
    assert ere_escape(raw) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("msg\n\nHse-Kind: edit", "edit"),
        ("msg\n\nHse-Kind:   compile  ", "compile"),
        ("msg\n\nHse-Kind-Other: edit", None),
        ("msg", None),
    ],
)
def test__raw_kind__reads_the_trailer(body: str, expected: str | None) -> None:
    assert raw_kind(body) == expected


@pytest.mark.parametrize(
    ("body", "kinds", "expected"),
    [
        ("m\n\nHse-Kind: edit", ("edit",), True),
        ("m\n\nHse-Kind: edit", ("manual",), False),
        ("m", ("manual",), True),
        ("m\n\nHse-Kind: from-the-future", ("manual",), True),
        ("m\n\nHse-Kind: from-the-future", ("edit",), False),
        ("m\n\nHse-Kind: from-the-future", ("from-the-future",), True),
    ],
)
def test__kind_matches__treats_missing_and_unknown_kinds_as_manual(
    body: str, kinds: tuple[str, ...], expected: bool
) -> None:
    assert kind_matches(body, kinds) is expected


def test__git_args__empty_query_adds_nothing() -> None:
    assert git_args(VcsHistoryQuery()) == []


def test__git_args__kind_author_and_dates() -> None:
    query = VcsHistoryQuery(
        kinds=("edit", "compile"),
        author_email="a.b@x.ru",
        since=datetime(2026, 2, 1, 12, 0, tzinfo=timezone(timedelta(hours=3))),
        until=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert git_args(query) == [
        "--extended-regexp",
        "--grep=^Hse-Kind: (edit|compile)$",
        "--extended-regexp",
        "--regexp-ignore-case",
        r"--author=<a\.b@x\.ru>",
        "--since=2026-02-01 09:00:00 +0000",
        "--until=2026-03-01 00:00:00 +0000",
    ]


def test__git_args__manual_kind_is_left_to_python() -> None:
    query = VcsHistoryQuery(kinds=("manual", "edit"))

    assert git_args(query) == []
    assert needs_python(query)
    assert not needs_python(VcsHistoryQuery(kinds=("edit",)))


def test__matches__text_ignores_case_whitespace_and_service_trailers() -> None:
    body = "Правки  Введения\n\nHse-Kind: edit"

    assert matches(body, VcsHistoryQuery(text="правки введения"))
    assert not matches(body, VcsHistoryQuery(text="edit"))
    assert not matches(body, VcsHistoryQuery(text="заключение"))
    assert matches(body, VcsHistoryQuery(text="  "))
