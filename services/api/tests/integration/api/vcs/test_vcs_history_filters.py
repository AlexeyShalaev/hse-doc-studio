from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.git_sync import HistoryCommitResponse, HistoryFacetsResponse
from httpx import AsyncClient

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID

_MARIA = ("Maria Ivanova", "m.ivanova@edu.hse.ru")


def _commit(project: dict[str, Any], message: str, author: tuple[str, str] = _MARIA) -> None:
    """Коммит напрямую в хранилище проекта: как от другого автора или без трейлера Hse-Kind."""
    folder = Path(project["folder"])
    env = {
        "PATH": os.environ["PATH"],
        "GIT_AUTHOR_NAME": author[0],
        "GIT_AUTHOR_EMAIL": author[1],
        "GIT_COMMITTER_NAME": author[0],
        "GIT_COMMITTER_EMAIL": author[1],
    }
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "--git-dir",
            str(folder / ".hse-studio" / "git"),
            "--work-tree",
            str(folder),
            "commit",
            "--allow-empty",
            "-m",
            message,
        ],
        check=True,
        capture_output=True,
        env=env,
    )


def _url(project: dict[str, Any], tail: str = "history") -> str:
    return f"/api/v1/projects/{project['id']}/vcs/{tail}"


async def test__api__history__commits_carry_author_email_merge_flag_and_null_sync(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    _commit(project, "Введение\n\nHse-Kind: edit")

    resp = await test_app.get(_url(project))

    assert resp.status_code == 200, resp.text
    commits = resp.json()
    assert [c["message"] for c in commits] == ["Введение", "Создание проекта"]
    assert commits[0]["author_email"] == _MARIA[1]
    assert commits[0]["is_merge"] is False
    assert commits[0]["sync"] is None
    for commit in commits:
        HistoryCommitResponse.model_validate(commit)


async def test__api__history__filters_by_repeated_kind_author_and_text(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    _commit(project, "Введение\n\nHse-Kind: edit")
    _commit(project, "Сборка\n\nHse-Kind: compile")
    _commit(project, "Слияние\n\nHse-Kind: sync")
    _commit(project, "Введение (Анна)\n\nHse-Kind: edit", ("Anna", "a@x.ru"))

    by_kinds = await test_app.get(_url(project), params=[("kind", "edit"), ("kind", "compile")])
    by_author = await test_app.get(_url(project), params={"author_email": "a@x.ru"})
    by_text = await test_app.get(_url(project), params={"q": "ВВЕДЕНИЕ", "kind": "edit"})
    manual = await test_app.get(_url(project), params={"kind": "manual"})

    assert [c["message"] for c in by_kinds.json()] == ["Введение (Анна)", "Сборка", "Введение"]
    assert [c["message"] for c in by_author.json()] == ["Введение (Анна)"]
    assert [c["message"] for c in by_text.json()] == ["Введение (Анна)", "Введение"]
    assert manual.json() == []


async def test__api__history__pages_through_a_filtered_list(test_app: AsyncClient, project: dict[str, Any]) -> None:
    for i in range(5):
        _commit(project, f"edit {i}\n\nHse-Kind: edit")
        _commit(project, f"build {i}\n\nHse-Kind: compile")

    first = await test_app.get(_url(project), params={"kind": "edit", "limit": 2})
    second = await test_app.get(_url(project), params={"kind": "edit", "limit": 2, "offset": 2})
    last = await test_app.get(_url(project), params={"kind": "edit", "limit": 2, "offset": 4})

    assert [c["message"] for c in first.json()] == ["edit 4", "edit 3"]
    assert [c["message"] for c in second.json()] == ["edit 2", "edit 1"]
    assert [c["message"] for c in last.json()] == ["edit 0"]


async def test__api__history__filters_by_date_range(test_app: AsyncClient, project: dict[str, Any]) -> None:
    resp_all = await test_app.get(_url(project), params={"since": "2000-01-01T00:00:00Z"})
    resp_none = await test_app.get(_url(project), params={"until": "2000-01-01T00:00:00Z"})

    assert len(resp_all.json()) == 1
    assert resp_none.json() == []


async def test__api__history__sync_filter_without_remote(test_app: AsyncClient, project: dict[str, Any]) -> None:
    all_ = await test_app.get(_url(project), params={"sync": "all"})
    unpushed = await test_app.get(_url(project), params={"sync": "unpushed"})
    incoming = await test_app.get(_url(project), params={"sync": "incoming"})

    assert len(all_.json()) == 1
    assert all_.json()[0]["sync"] is None
    assert unpushed.json() == []
    assert incoming.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"kind": "Edit"},
        {"kind": "a b"},
        {"kind": ""},
        {"sync": "everything"},
        {"since": "yesterday"},
        {"q": "x" * 201},
        {"limit": 0},
    ],
    ids=["uppercase_kind", "kind_with_space", "empty_kind", "unknown_sync", "bad_date", "long_query", "zero_limit"],
)
async def test__api__history__invalid_filter__returns_422(
    test_app: AsyncClient, project: dict[str, Any], params: dict[str, Any]
) -> None:
    resp = await test_app.get(_url(project), params=params)

    assert resp.status_code == 422


async def test__api__history_facets__counts_kinds_and_authors(test_app: AsyncClient, project: dict[str, Any]) -> None:
    _commit(project, "a\n\nHse-Kind: edit")
    _commit(project, "b\n\nHse-Kind: edit", ("Anna", "a@x.ru"))
    _commit(project, "c\n\nHse-Kind: sync")

    resp = await test_app.get(_url(project, "history/facets"))

    assert resp.status_code == 200, resp.text
    body = HistoryFacetsResponse.model_validate(resp.json())
    assert body.kinds == {"init": 1, "edit": 2, "sync": 1}
    emails = {a.email: a.count for a in body.authors}
    assert emails[_MARIA[1]] == 2
    assert emails["a@x.ru"] == 1
    assert [a.count for a in body.authors] == sorted((a.count for a in body.authors), reverse=True)


async def test__api__history_facets__unknown_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/history/facets")

    assert resp.status_code == 404
