"""Куда вести после принятия приглашения: только относительный путь этого сайта (`?next=`)."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.invitations.policy import safe_next_path
from hse_doc_studio.use_cases.projects.invitations import invitation_link


@pytest.mark.parametrize("path", ["/sign/p/r", "/projects/p?tab=signatures", " /sign/p/r "])
def test__safe_next_path__relative_site_path__kept(path: str) -> None:
    assert safe_next_path(path) == path.strip()


@pytest.mark.parametrize(
    "path",
    [
        "//evil.example/x",
        "/\\evil.example",
        "https://evil.example",
        "sign/p/r",
        "/a:b",
        "/x\nSet-Cookie",
        "/" + "a" * 600,
    ],
)
def test__safe_next_path__anything_else__dropped(path: str) -> None:
    assert safe_next_path(path) is None


def test__invitation_link__next__url_encoded_query() -> None:
    assert invitation_link("https://studio.example/", "tok", "/sign/p/r") == (
        "https://studio.example/project-invite/tok?next=%2Fsign%2Fp%2Fr"
    )
    assert invitation_link("https://studio.example", "tok") == "https://studio.example/project-invite/tok"
