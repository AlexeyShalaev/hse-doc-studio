"""Чистые правила потока предложения (срез T6): имя ветки, сообщение, push options, compare, сводка проверок."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.git_sync.providers import GitProvider
from hse_doc_studio.core.pack_studio.git_flow import (
    ChangeStatus,
    CheckState,
    CheckSummary,
    CiCheck,
    CiState,
    FileChange,
    ForkRef,
    HostingRepo,
    VersionSummary,
    changed_versions,
    checks_page_url,
    compare_url,
    default_commit_message,
    gitlab_push_options,
    merge_request_from_output,
    proposal_body,
    repo_key,
    repo_path_of,
    slug,
    summarize_checks,
    touched_scopes,
    work_branch_name,
)
from hse_doc_studio.core.pack_studio.paths import VersionRef

NOW = datetime(2026, 11, 15, 9, 30, tzinfo=UTC)
V7 = VersionRef("hse-cs-sse", "coursework", "2026.1.7")


def _change(path: str, status: ChangeStatus = ChangeStatus.modified) -> FileChange:
    return FileChange(path, status)


def test__changed_versions__unique_in_path_order() -> None:
    changes = [
        _change("hse-cs-sse/templates/coursework/versions/2026.1.7/version.yaml"),
        _change("hse-cs-sse/templates/coursework/versions/2026.1.7/files/a.tex"),
        _change("hse-cs-sse/pack.yaml"),
        _change("hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml"),
    ]

    assert [ref.dir for ref in changed_versions(changes)] == [
        "hse-cs-sse/templates/coursework/versions/2026.1.7",
        "hse-cs-se/templates/vkr/versions/2026.1.2",
    ]


def test__touched_scopes__template_for_template_paths_pack_for_pack_files() -> None:
    changes = [
        _change("hse-cs-sse/templates/coursework/versions/2026.1.7/version.yaml"),
        _change("hse-cs-sse/templates/coursework/template.yaml"),
        _change("hse-cs-sse/pack.yaml"),
        _change("README.md"),
    ]

    assert touched_scopes(changes) == ("hse-cs-sse/templates/coursework", "hse-cs-sse")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("anna.ivanova", "anna.ivanova"), ("Анна Иванова", "author"), ("Ivan  Petrov!!", "ivan-petrov"), ("--", "author")],
)
def test__slug__ascii_only_with_fallback(text: str, expected: str) -> None:
    assert slug(text, fallback="author") == expected


def test__work_branch_name__one_version__named_after_it_and_unique() -> None:
    first = work_branch_name("anna", [V7], NOW)
    second = work_branch_name("anna", [V7], NOW, taken=[first])

    assert first == "pack-studio/anna/hse-cs-sse-coursework-2026.1.7"
    assert second == f"{first}-2"


def test__work_branch_name__several_versions__uses_time() -> None:
    other = VersionRef("hse-cs-se", "vkr", "2026.1.2")

    assert work_branch_name("anna", [V7, other], NOW) == "pack-studio/anna/20261115-0930"


@pytest.mark.parametrize(
    ("classes", "prefix"),
    [(["patch"], "fix(packs)"), (["patch", "minor"], "feat(packs)"), ([None], "feat(packs)")],
)
def test__default_commit_message__conventional_by_class(classes: list[str | None], prefix: str) -> None:
    summaries = [VersionSummary(ref=V7, suggested=cls) for cls in classes]

    assert default_commit_message(summaries).startswith(f"{prefix}: hse-cs-sse/coursework 2026.1.7")


def test__default_commit_message__no_versions__chore() -> None:
    assert default_commit_message([]).startswith("chore(packs):")


def test__proposal_body__versions_class_notes_checks_and_proposer() -> None:
    summary = VersionSummary(
        ref=V7,
        released_base="2026.1.6",
        minimum="patch",
        suggested="minor",
        headline={"ru": "Класс minor: новое поле."},
        reasons=({"ru": "Добавлено поле x", "en": "Field x added"},),
        changes={"ru": ("Новое поле.",), "en": ("A new field.",)},
    )

    body = proposal_body([summary], CheckSummary(errors=0, warnings=2), proposed_by="Анна", extra="Смотрите места.")

    assert body.startswith("Смотрите места.")
    assert "### hse-cs-sse / coursework 2026.1.7" in body
    assert "Класс: **minor** (от 2026.1.6)" in body
    assert "Минимум по изменениям: patch" in body
    assert "- Добавлено поле x" in body
    assert "Изменения:\n- Новое поле." in body
    assert "Changes:\n- A new field." in body
    assert "предупреждений 2" in body
    assert body.endswith("Предложено в Студии шаблонов пользователем Анна.")


def test__gitlab_push_options__one_line_values() -> None:
    options = gitlab_push_options(target_branch="main", title="fix(packs):\nx", description="a\nb\n\nc")

    assert options == [
        "merge_request.create",
        "merge_request.target=main",
        "merge_request.title=fix(packs): x",
        "merge_request.description=a b c",
        "merge_request.remove_source_branch",
    ]


def test__merge_request_from_output__parses_gitlab_remote_line() -> None:
    text = "remote:\nremote: View merge request for b:\nremote:   https://gl.example/g/p/-/merge_requests/42\n"

    found = merge_request_from_output(text)

    assert found is not None
    assert (found.number, found.url) == (42, "https://gl.example/g/p/-/merge_requests/42")
    assert merge_request_from_output("To https://gl.example/g/p.git") is None


_GH = HostingRepo(GitProvider.github, "acme/packs", "https://github.com", "https://api.github.com")
_GL = HostingRepo(GitProvider.gitlab, "fcs/team/packs", "https://git.hse.ru/gitlab", "https://git.hse.ru/gitlab/api/v4")


def test__compare_url__github_same_repo_and_fork() -> None:
    fork = ForkRef("anna/packs", "https://github.com/anna/packs.git")

    assert compare_url(_GH, base="main", branch="pack-studio/a/b", fork=None) == (
        "https://github.com/acme/packs/compare/main...pack-studio/a/b?expand=1"
    )
    assert compare_url(_GH, base="main", branch="x", fork=fork) == (
        "https://github.com/acme/packs/compare/main...anna:x?expand=1"
    )


def test__compare_url__gitlab_new_merge_request_page_and_other_provider_none() -> None:
    other = HostingRepo(GitProvider.other, "a/b", None, None)

    assert compare_url(_GL, base="main", branch="p/s", fork=None) == (
        "https://git.hse.ru/gitlab/fcs/team/packs/-/merge_requests/new?merge_request%5Bsource_branch%5D=p%2Fs"
    )
    assert compare_url(other, base="main", branch="x", fork=None) is None


def test__checks_page_url__by_provider() -> None:
    assert checks_page_url(_GH, branch="b", sha="abc") == "https://github.com/acme/packs/commit/abc/checks"
    assert (
        checks_page_url(_GL, branch="p/s", sha="abc")
        == "https://git.hse.ru/gitlab/fcs/team/packs/-/pipelines?ref=p%2Fs"
    )


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ([], CiState.none),
        ([CheckState.success, CheckState.skipped], CiState.success),
        ([CheckState.success, CheckState.running], CiState.pending),
        ([CheckState.running, CheckState.failure], CiState.failure),
        ([CheckState.cancelled], CiState.failure),
    ],
)
def test__summarize_checks__failure_beats_pending_beats_success(states: list[CheckState], expected: CiState) -> None:
    assert summarize_checks([CiCheck(name=str(i), state=s) for i, s in enumerate(states)]) == expected


def test__repo_path_of__strips_git_suffix_and_install_prefix() -> None:
    assert repo_path_of("https://github.com/acme/packs.git", "https://github.com") == "acme/packs"
    assert repo_path_of("https://git.hse.ru/gitlab/fcs/packs.git", "https://git.hse.ru/gitlab") == "fcs/packs"
    assert repo_path_of("https://git.hse.ru/gitlab/fcs/packs", None) == "gitlab/fcs/packs"


def test__repo_key__case_and_suffix_insensitive() -> None:
    assert repo_key("GitLab.example.org", None, "FCS/packs.git") == repo_key("gitlab.example.org", None, "fcs/packs/")
    assert repo_key("h", 8443, "a/b") != repo_key("h", None, "a/b")
