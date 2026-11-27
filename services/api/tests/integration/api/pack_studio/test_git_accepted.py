"""Принятая версия: запрос слит, а базу после этого не выбирали. Версия не черновик, а «принята, обновите пространство».

git настоящий (file://), хостинга нет: ответ «Предложить» получает номер запроса, а состояние запроса подменено.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from hse_doc_studio.core.pack_studio.git_flow import PullRequestInfo, PullRequestRef, PullRequestState
from hse_doc_studio.infra.pack_studio.hosting import HttpPackHosting
from hse_doc_studio.use_cases.pack_studio.git import PackGitService

from tests.fixtures.git_remote import BareRemote
from tests.integration.api.pack_studio.conftest import API, DRAFT, DRAFT_DIR, TEMPLATE_DIR, Stand
from tests.integration.api.pack_studio.test_git_flow import _git, _git_url, _put, _ready, _refresh

_TEX = f"{DRAFT_DIR}/files/report/main.tex"
_PROPOSED_TEX = b"\\documentclass{article}\n% proposed\n"
_VERSION_URL = f"demo/report/{DRAFT}"


@dataclass
class Hosting:
    """Запрос у хостинга: состояние и вершина его ветки."""

    state: PullRequestState = PullRequestState.merged
    head_sha: str | None = None


def fake_pull_requests(monkeypatch: pytest.MonkeyPatch) -> Hosting:
    """«Предложить» открывает запрос №531, повторная отправка новый не открывает (как без права на PR)."""
    hosting = Hosting()
    opened: list[int] = []

    async def open_once(*_args: Any) -> tuple[PullRequestRef | None, None]:
        if opened:
            return None, None
        opened.append(531)
        return PullRequestRef(number=531, url="https://example.org/pull/531"), None

    async def pull_request(*_args: Any) -> PullRequestInfo:
        return PullRequestInfo(hosting.state, hosting.head_sha)

    monkeypatch.setattr(PackGitService, "_pull_request", open_once)
    monkeypatch.setattr(HttpPackHosting, "pull_request", pull_request)
    return hosting


def _version_url(ws_id: str, tail: str) -> str:
    return f"{API}/workspaces/{ws_id}/versions/{_VERSION_URL}/{tail}"


async def _proposed(stand: Stand, hosting: Hosting, *, release: bool = True) -> tuple[BareRemote, str, str]:
    """Черновик поправлен, выпущен (если `release`) и отправлен запросом. Возвращает вершину запроса."""
    remote, ws_id = await _ready(stand)
    await _put(stand, ws_id, _TEX, _PROPOSED_TEX)
    if release:
        notes = {"changes": {"ru": ["Правка титула."], "en": ["Title page fix."]}}
        saved = await stand.client.put(_version_url(ws_id, "notes"), json=notes)
        assert saved.status_code == 200, saved.text
        released = await stand.client.post(_version_url(ws_id, "release"), json={"set_default": True})
        assert released.status_code == 200, released.text
    resp = await stand.client.post(_git_url(ws_id, "/propose"), json={})
    assert resp.status_code == 200, resp.text
    hosting.head_sha = resp.json()["pushed_sha"]
    return remote, ws_id, str(resp.json()["pushed_sha"])


async def _accepted(stand: Stand, ws_id: str) -> list[str]:
    resp = await stand.client.get(_git_url(ws_id, "/checks"))
    assert resp.status_code == 200, resp.text
    return list(resp.json()["accepted_versions"])


async def _is_released(stand: Stand, ws_id: str) -> bool:
    tree = (await stand.client.get(f"{API}/workspaces/{ws_id}/tree")).json()
    return next(
        bool(v["released"])
        for p in tree["packs"]
        for t in p["templates"]
        for v in t["versions"]
        if v["version"] == DRAFT
    )


async def test__merged__stale_base__version_is_accepted_until_refresh(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    remote, ws_id, sha = await _proposed(stand, hosting)
    # Запрос слит на хостинге, пространство об этом базой ещё не знает.
    remote.git("update-ref", "refs/heads/main", sha)

    assert await _is_released(stand, ws_id) is False
    assert await _accepted(stand, ws_id) == [DRAFT_DIR]

    await _refresh(stand, ws_id)

    assert await _is_released(stand, ws_id) is True
    assert await _accepted(stand, ws_id) == []


@pytest.mark.parametrize("state", [PullRequestState.closed, PullRequestState.open])
async def test__not_merged__not_accepted(
    stand: Stand, monkeypatch: pytest.MonkeyPatch, state: PullRequestState
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    _, ws_id, _ = await _proposed(stand, hosting)
    hosting.state = state

    assert await _accepted(stand, ws_id) == []


@pytest.mark.parametrize(
    "edit",
    [
        pytest.param(lambda: (_TEX, b"\\documentclass{article}\n% after merge\n"), id="changed-file"),
        pytest.param(lambda: (f"{DRAFT_DIR}/files/report/late.tex", b"late\n"), id="new-file"),
    ],
)
async def test__merged__edit_of_the_version_after_merge__not_accepted(
    stand: Stand, monkeypatch: pytest.MonkeyPatch, edit: Callable[[], tuple[str, bytes]]
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    _, ws_id, _ = await _proposed(stand, hosting)
    assert await _accepted(stand, ws_id) == [DRAFT_DIR]
    path, content = edit()

    await _put(stand, ws_id, path, content)
    unsaved = await _accepted(stand, ws_id)
    committed = await stand.client.post(_git_url(ws_id, "/commit"), json={})

    assert committed.json()["committed"] is True
    assert unsaved == []
    assert await _accepted(stand, ws_id) == []


async def test__merged__edit_pushed_again_without_a_new_request__not_accepted(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    _, ws_id, merged_sha = await _proposed(stand, hosting, release=False)
    # Версия выпущена уже после слияния и отправлена снова: номер запроса прежний, а `pushed_sha` новый.
    notes = {"changes": {"ru": ["Правка титула."], "en": ["Title page fix."]}}
    await stand.client.put(_version_url(ws_id, "notes"), json=notes)
    released = await stand.client.post(_version_url(ws_id, "release"), json={})
    assert released.status_code == 200, released.text
    again = await stand.client.post(_git_url(ws_id, "/propose"), json={})
    assert again.status_code == 200, again.text
    assert again.json()["git"]["workspace"]["pr_number"] == 531
    assert again.json()["pushed_sha"] != merged_sha

    assert await _accepted(stand, ws_id) == []


async def test__merged__request_head_unknown_here__compared_with_what_the_studio_pushed(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    _, ws_id, _ = await _proposed(stand, hosting)
    # В ветку запроса дописали на хостинге: такой вершины в хранилище пространства нет.
    hosting.head_sha = "f" * 40

    assert await _accepted(stand, ws_id) == [DRAFT_DIR]


async def test__merged__version_proposed_without_release__stays_a_draft(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    _, ws_id, _ = await _proposed(stand, hosting, release=False)

    assert await _accepted(stand, ws_id) == []


async def test__merged__start_over_still_works_and_forgets_the_request(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    remote, ws_id, sha = await _proposed(stand, hosting)
    remote.git("update-ref", "refs/heads/main", sha)

    resp = await stand.client.post(_git_url(ws_id, "/start-over"), json={})

    assert resp.status_code == 200, resp.text
    git = await _git(stand, ws_id)
    assert git["branch"] is None
    assert git["workspace"]["pr_number"] is None
    assert git["changed"] == []
    assert await _accepted(stand, ws_id) == []
    assert await _is_released(stand, ws_id) is True
    assert (await stand.client.get(stand.file_url(ws_id, f"{TEMPLATE_DIR}/releases.yaml"))).status_code == 200
