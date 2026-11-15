"""Официальные паки (срез T22): адрес из настроек, совпадение пространства, пути вне папки паков, ожидание одобрения."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.pack_studio.git_flow import CheckState, CiCheck, CiState, proposal_body, summarize_checks
from hse_doc_studio.core.pack_studio.official import official_repo, outside_packs, url_key

URL = "https://github.com/AlexeyShalaev/hse-doc-studio"


def _repo(url: str | None = URL) -> object:
    return official_repo(url, packs_path="packs", base_branch="master", license="Apache-2.0")


def test__official_repo__default_address__links_license_and_contributing() -> None:
    repo = official_repo(URL, packs_path="packs/", base_branch="master", license="Apache-2.0")

    assert repo is not None
    assert repo.packs_path == "packs"
    assert repo.web_url == URL
    assert repo.license_url == f"{URL}/blob/master/LICENSE"
    assert repo.contributing_url == f"{URL}/blob/master/CONTRIBUTING.md#contributing-to-the-official-packs"


@pytest.mark.parametrize(
    "url", ["", "   ", None, "http://github.com/a/b", "git@github.com:a/b.git", "https://github.com"]
)
def test__official_repo__empty_or_not_https__hides_the_button(url: str | None) -> None:
    assert _repo(url) is None


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/AlexeyShalaev/hse-doc-studio.git",
        "https://GitHub.com/alexeyshalaev/HSE-doc-studio/",
        URL,
    ],
)
def test__matches__same_repository_ignoring_case_and_dot_git(remote: str) -> None:
    repo = official_repo(URL, packs_path="packs", base_branch="master", license="Apache-2.0")

    assert repo is not None
    assert repo.matches(remote)


@pytest.mark.parametrize(
    "remote", ["https://github.com/bot/hse-doc-studio.git", "https://gitlab.com/AlexeyShalaev/hse-doc-studio", None]
)
def test__matches__fork_or_other_host__is_not_official(remote: str | None) -> None:
    repo = official_repo(URL, packs_path="packs", base_branch="master", license="Apache-2.0")

    assert repo is not None
    assert not repo.matches(remote)


def test__url_key__fork_and_upstream_differ() -> None:
    assert url_key("https://github.com/bot/hse-doc-studio.git") != url_key(URL)
    assert url_key("ssh://git@github.com/a/b.git") is None


def test__outside_packs__keeps_only_paths_outside_the_folder() -> None:
    paths = ["packs/hse-cs-sse/pack.yaml", ".github/workflows/ci.yml", "packsX/evil", "README.md", "packs/a/b"]

    assert outside_packs(paths, "packs") == (".github/workflows/ci.yml", "README.md", "packsX/evil")
    assert outside_packs(paths, ".") == ()


def test__summarize__approval_waits_over_running_but_failure_wins() -> None:
    waiting = CiCheck("CI", CheckState.awaiting_approval)
    running = CiCheck("lint", CheckState.running)
    failed = CiCheck("build", CheckState.failure)

    assert summarize_checks([waiting, running]) is CiState.awaiting_approval
    assert summarize_checks([waiting, failed]) is CiState.failure


def test__proposal_body__via_bot__names_author_without_email() -> None:
    body = proposal_body([], None, proposed_by="Анна Иванова", via_bot="https://studio.example.org")

    assert "пользователем Анна Иванова" in body
    assert "служебным аккаунтом установки Студии (https://studio.example.org)" in body
    assert "@" not in body
