from __future__ import annotations

from uuid import uuid4

import pytest
from hse_doc_studio.core.git_sync.entities import StoreRemoteConfig, SyncState
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.use_cases.git_sync.status import default_state, fetch_interval, web_url_of

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://github.com/hse-team/course-paper.git", "https://github.com/hse-team/course-paper"),
        ("https://github.com/hse-team/course-paper", "https://github.com/hse-team/course-paper"),
        ("https://gitlab.hse.local/gitlab/group/repo.git", "https://gitlab.hse.local/gitlab/group/repo"),
        ("git@github.com:hse-team/course-paper.git", "https://github.com/hse-team/course-paper"),
        ("ssh://git@git.hse.ru:2222/hse-team/course-paper.git", "https://git.hse.ru/hse-team/course-paper"),
        ("https://user:ghp_secret@github.com/a/b.git", "https://github.com/a/b"),
    ],
)
def test__web_url_of__builds_the_page_of_the_repository(raw: str, expected: str) -> None:
    assert web_url_of(parse_remote_url(raw)) == expected


def test__web_url_of__local_repositories_have_no_page() -> None:
    assert web_url_of(parse_remote_url("file:///srv/git/project.git", allow_local=True)) is None


def test__default_state__fills_missing_state_from_the_store_config() -> None:
    credential = uuid4()
    config = StoreRemoteConfig(url="x", credential_id=credential, local_branch="draft", remote_branch="dev")

    from_config = default_state(config, "master")
    bare = default_state(StoreRemoteConfig(url="x"), "master")
    detached = default_state(StoreRemoteConfig(url="x"), None)

    assert (from_config.local_branch, from_config.remote_branch, from_config.credential_id) == (
        "draft",
        "dev",
        credential,
    )
    assert (bare.local_branch, bare.remote_branch) == ("master", "main")
    assert detached.local_branch == "main"


@pytest.mark.parametrize(
    ("state", "stored", "expected"),
    [
        (None, {}, (True, 300)),
        (None, {"git_fetch_interval_s": 900}, (True, 900)),
        (None, {"git_fetch_interval_s": 0}, (False, 300)),
        (SyncState("a", "b", auto_fetch=False), {"git_fetch_interval_s": 600}, (False, 600)),
        (SyncState("a", "b", fetch_interval_s=120), {"git_fetch_interval_s": 600}, (True, 120)),
        (SyncState("a", "b", fetch_interval_s=30), {"git_fetch_interval_s": 600}, (True, 60)),
        (SyncState("a", "b", fetch_interval_s=120), {"git_fetch_interval_s": 0}, (False, 300)),
        (None, {"git_fetch_interval_s": "oops"}, (True, 300)),
        (None, {"git_fetch_interval_s": True}, (True, 300)),
    ],
)
def test__fetch_interval__general_setting_off_wins_then_project_override(
    state: SyncState | None, stored: dict[str, object], expected: tuple[bool, int]
) -> None:
    assert fetch_interval(state, stored) == expected
