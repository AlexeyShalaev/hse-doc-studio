"""Официальные паки (срез T22): кнопка, вклад своим токеном через форк, согласие с лицензией, только папка паков.

Сценарий `PackGitService` и `OfficialPacks` на фейках портов: ни git, ни хостинга, ни сети. Push и PR записываются
фейками, по ним проверяется, куда ушла ветка и что видно в PR. Бота установки нет: PR в официальные паки создают
только люди своим аккаунтом.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.providers import GitProvider
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.core.pack_studio.entities import PackWorkspace, WorkspaceKind, WorkspaceState
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.git_flow import (
    ChangeStatus,
    CheckState,
    CiCheck,
    CiReport,
    CiState,
    FileChange,
    ForkRef,
    PullRequestInfo,
    PullRequestRef,
    PullRequestState,
    PushOutcome,
    RepoPermissions,
    WorkGitStatus,
)
from hse_doc_studio.core.pack_studio.official import official_repo
from hse_doc_studio.core.pack_studio.protocols import PackCheckReport, VersionNotes
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.use_cases.pack_studio.git import AUDIT_PROPOSED, PackGitService, ProposeInput
from hse_doc_studio.use_cases.pack_studio.official import AUDIT_LICENSE, OFFICIAL_LABEL, OfficialPacks
from hse_doc_studio.use_cases.pack_studio.workspaces import WorkspaceView

UPSTREAM = "https://github.com/AlexeyShalaev/hse-doc-studio"
ANNA_FORK = "https://github.com/anna/hse-doc-studio.git"
ANNA = Actor.user("u_anna", "Анна Иванова", "anna@real.example.org")
REAL_EMAIL = "anna@real.example.org"
CHANGED = "hse-cs-sse/templates/coursework/versions/2026.1.8/version.yaml"
NOW = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def _workspace(**changes: Any) -> PackWorkspace:
    """Официальное пространство Анны своим токеном, форк уже известен (поток T6)."""
    base = PackWorkspace(
        id=uuid4(),
        owner_id="u_anna",
        kind=WorkspaceKind.git,
        label=OFFICIAL_LABEL,
        packs_path="packs",
        created_at=NOW,
        updated_at=NOW,
        state=WorkspaceState.ready,
        remote_url=UPSTREAM,
        base_branch="master",
        credential_id=uuid4(),
        fork_url=ANNA_FORK,
    )
    return replace(base, **changes)


# ── фейки портов ─────────────────────────────────────────────────────────────


class _Tasks:
    async def exclusive(self, _workspace_id: UUID, work: Any) -> Any:
        return await work()


class _Workspaces:
    def __init__(self, ws: PackWorkspace | None) -> None:
        self.items: dict[UUID, PackWorkspace] = {} if ws is None else {ws.id: ws}
        self.tasks = _Tasks()
        self.created: list[Any] = []

    async def git_ready(self, _actor: Actor, workspace_id: UUID) -> PackWorkspace:
        return self.items[workspace_id]

    def dirs_of(self, ws: PackWorkspace) -> Any:
        return SimpleNamespace(root=Path("/nowhere") / str(ws.id))

    def target_of(self, ws: PackWorkspace) -> RemoteTarget:
        return RemoteTarget(url=parse_remote_url(ws.remote_url or ""), credential_id=ws.service_access_id)

    def packs_root(self, _ws: PackWorkspace) -> Path:
        return Path("/nowhere/packs")

    async def save(self, ws: PackWorkspace) -> PackWorkspace:
        self.items[ws.id] = ws
        return ws

    async def list(self, _actor: Actor) -> list[WorkspaceView]:
        return [WorkspaceView(workspace=ws, busy=False) for ws in self.items.values()]

    async def get(self, _actor: Actor, workspace_id: UUID) -> WorkspaceView:
        return WorkspaceView(workspace=self.items[workspace_id], busy=False)

    async def create(self, _actor: Actor, inp: Any) -> WorkspaceView:
        self.created.append(inp)
        ws = _workspace(id=uuid4(), credential_id=inp.credential_id, state=WorkspaceState.cloning)
        self.items[ws.id] = ws
        return WorkspaceView(workspace=ws, busy=True)


@dataclass
class _Git:
    branch_files: tuple[str, ...] = (f"packs/{CHANGED}",)
    branch: str | None = None
    dirty: bool = True
    pushes: list[RemoteTarget] = field(default_factory=list)
    authors: list[VcsAuthor] = field(default_factory=list)

    async def status(self, _dirs: Any, _target: Any, *, base_branch: str, packs_path: str) -> WorkGitStatus:
        change = FileChange(CHANGED, ChangeStatus.modified)
        return WorkGitStatus(
            head_sha="c" * 40,
            branch=self.branch,
            uncommitted=(change,) if self.dirty else (),
            changed=(change,),
            ahead=0 if self.dirty else 1,
            behind=0,
        )

    async def local_branches(self, _dirs: Any) -> tuple[str, ...]:
        return ()

    async def create_branch(self, _dirs: Any, *, name: str) -> None:
        self.branch = name

    async def commit(self, _dirs: Any, _target: Any, *, packs_path: str, message: str, author: VcsAuthor) -> str | None:
        self.authors.append(author)
        self.dirty = False
        return "c" * 40

    async def branch_paths(self, _dirs: Any, *, base_branch: str) -> tuple[str, ...]:
        return self.branch_files

    async def base_registries(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {}

    async def changed_since(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def push(self, _dirs: Any, target: RemoteTarget, *, branch: str, push_options: Any = ()) -> PushOutcome:
        self.pushes.append(target)
        return PushOutcome(sha="c" * 40, remote_output="")


@dataclass
class _Hosting:
    can_push: bool | None = False
    pulls: list[dict[str, str]] = field(default_factory=list)
    forks_made: int = 0
    ci: CiReport | None = None
    pr_state: PullRequestState | None = None

    async def permissions(self, *_args: Any) -> RepoPermissions:
        return RepoPermissions(can_push=self.can_push)

    async def fork(self, _repo: Any, _target: RemoteTarget, *, create: bool) -> ForkRef | None:
        self.forks_made += 1
        return ForkRef(path="anna/hse-doc-studio", clone_url=ANNA_FORK)

    async def open_pull_request(self, _repo: Any, target: RemoteTarget, **kwargs: str) -> PullRequestRef:
        self.pulls.append({**kwargs, "target": target.url.display_url})
        return PullRequestRef(number=412, url=f"{UPSTREAM}/pull/412")

    async def ci_status(self, _repo: Any, _target: Any, *, sha: str, branch: str | None) -> CiReport:
        return self.ci or CiReport(state=CiState.none, sha=sha)

    async def pull_request(self, *_args: Any) -> PullRequestInfo | None:
        return None if self.pr_state is None else PullRequestInfo(self.pr_state)


class _Checker:
    def check(self, *_args: Any) -> PackCheckReport:
        return PackCheckReport()

    def notes(self, *_args: Any) -> VersionNotes:
        return VersionNotes(changes={})


class _Resolver:
    async def resolve(self, _url: Any) -> Any:
        return SimpleNamespace(
            info=SimpleNamespace(id=GitProvider.github), api_base="https://api.github.com", ca_file=None
        )

    async def known(self, *_args: Any) -> Any:
        return SimpleNamespace(id=GitProvider.github)


class _Transport:
    async def probe(self, _target: Any) -> Any:
        return SimpleNamespace(branches=("master",))


class _Author:
    def author(self) -> VcsAuthor:
        return VcsAuthor(name="Анна Иванова", email=REAL_EMAIL)


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def record(self, action: str, **kwargs: Any) -> None:
        self.events.append((action, kwargs))


@dataclass
class _Stand:
    ws: PackWorkspace
    workspaces: _Workspaces
    git: _Git
    hosting: _Hosting
    audit: _Audit
    official: OfficialPacks
    service: PackGitService

    @property
    def current(self) -> PackWorkspace:
        return self.workspaces.items[self.ws.id]


def _stand(
    *,
    ws: PackWorkspace | None = None,
    git: _Git | None = None,
    hosting: _Hosting | None = None,
) -> _Stand:
    workspace = ws or _workspace()
    workspaces = _Workspaces(workspace)
    audit = _Audit()
    repo = official_repo(UPSTREAM, packs_path="packs", base_branch="master", license="Apache-2.0")
    official = OfficialPacks(repo, workspaces, audit=audit)  # type: ignore[arg-type]
    the_git = git or _Git()
    the_hosting = hosting or _Hosting()
    service = PackGitService(
        workspaces,  # type: ignore[arg-type]
        the_git,  # type: ignore[arg-type]
        _Transport(),  # type: ignore[arg-type]
        the_hosting,  # type: ignore[arg-type]
        _Checker(),  # type: ignore[arg-type]
        _Resolver(),  # type: ignore[arg-type]
        _Author(),
        GitSyncPolicy(),
        diff_max_bytes=1024,
        audit=audit,  # type: ignore[arg-type]
        official=official,
    )
    return _Stand(workspace, workspaces, the_git, the_hosting, audit, official, service)


# ── своим токеном: куда уходит ветка и что видно в PR ────────────────────────


async def test__own_token__proposal__branch_to_own_fork_pr_into_official_signed_by_profile() -> None:
    stand = _stand()

    view = await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert [t.url.display_url for t in stand.git.pushes] == [ANNA_FORK]
    assert stand.hosting.forks_made == 0
    (pull,) = stand.hosting.pulls
    assert pull["target"] == UPSTREAM
    assert pull["head"].startswith("anna:pack-studio/")
    assert pull["base"] == "master"
    assert "пользователем Анна Иванова" in pull["body"]
    assert "служебным аккаунтом" not in pull["body"]
    assert stand.git.authors == [VcsAuthor(name="Анна Иванова", email=REAL_EMAIL)]
    assert view.pushed_to == ANNA_FORK


async def test__own_token__proposal__audited_as_official_without_bot_flag() -> None:
    stand = _stand()

    await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    proposed = [details for action, details in stand.audit.events if action == AUDIT_PROPOSED]
    assert len(proposed) == 1
    assert proposed[0]["actor_id"] == "u_anna"
    assert proposed[0]["details"]["official"] is True
    assert "bot" not in proposed[0]["details"]
    assert proposed[0]["details"]["pushed_to"] == ANNA_FORK


async def test__own_token__no_fork_and_no_push_right__fork_required_as_in_t6() -> None:
    stand = _stand(ws=_workspace(fork_url=None))

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert caught.value.code is PackStudioErrorCode.fork_required
    assert stand.git.pushes == []


# ── только папка паков ───────────────────────────────────────────────────────


async def test__official__branch_touches_files_outside_packs__refused() -> None:
    git = _Git(branch_files=(f"packs/{CHANGED}", ".github/workflows/ci.yml"))
    stand = _stand(git=git)

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert caught.value.code is PackStudioErrorCode.paths_outside_packs
    assert caught.value.ctx["files"] == [".github/workflows/ci.yml"]
    assert git.pushes == []


async def test__service_access_of_other_repository__branch_outside_packs__refused() -> None:
    git = _Git(branch_files=("README.md",))
    ws = _workspace(remote_url="https://github.com/acme/packs", credential_id=None, service_access_id=uuid4())
    stand = _stand(ws=ws, git=git, hosting=_Hosting(can_push=True))

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, ws.id, ProposeInput())

    assert caught.value.code is PackStudioErrorCode.paths_outside_packs
    assert git.pushes == []


async def test__own_token_in_other_repository__files_outside_packs__allowed() -> None:
    git = _Git(branch_files=("README.md",))
    ws = _workspace(remote_url="https://github.com/acme/packs", fork_url=None)
    stand = _stand(ws=ws, git=git, hosting=_Hosting(can_push=True))

    await stand.service.propose(ANNA, ws.id, ProposeInput())

    assert [t.url.display_url for t in git.pushes] == ["https://github.com/acme/packs"]


# ── согласие с лицензией ─────────────────────────────────────────────────────


async def test__official__first_proposal_without_consent__asks_with_license_links() -> None:
    stand = _stand()

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, stand.ws.id, ProposeInput())

    assert caught.value.code is PackStudioErrorCode.license_consent_required
    assert caught.value.ctx["license"] == "Apache-2.0"
    assert caught.value.ctx["license_url"] == f"{UPSTREAM}/blob/master/LICENSE"
    assert str(caught.value.ctx["contributing_url"]).startswith(f"{UPSTREAM}/blob/master/CONTRIBUTING.md#")
    assert stand.git.authors == []
    assert stand.git.pushes == []


async def test__official__consent_given_once__remembered_and_audited() -> None:
    stand = _stand()

    await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))
    stand.git.dirty = True
    await stand.service.propose(ANNA, stand.ws.id, ProposeInput())

    assert stand.current.license_accepted_at is not None
    assert [action for action, _ in stand.audit.events].count(AUDIT_LICENSE) == 1
    assert len(stand.git.pushes) == 2  # noqa: PLR2004


async def test__other_repository__no_consent_needed() -> None:
    ws = _workspace(remote_url="https://github.com/acme/packs", fork_url=None)
    stand = _stand(ws=ws, hosting=_Hosting(can_push=True))

    await stand.service.propose(ANNA, ws.id, ProposeInput())

    assert stand.current.license_accepted_at is None
    assert [t.url.display_url for t in stand.git.pushes] == ["https://github.com/acme/packs"]


# ── статус проверок и PR ─────────────────────────────────────────────────────


async def test__checks__awaiting_approval_and_merged_pr__passed_through() -> None:
    sha = "c" * 40
    ci = CiReport(state=CiState.awaiting_approval, sha=sha, checks=(CiCheck("CI", CheckState.awaiting_approval),))
    ws = _workspace(pushed_sha=sha, pr_number=412, work_branch="pack-studio/x")
    stand = _stand(ws=ws, hosting=_Hosting(ci=ci, pr_state=PullRequestState.merged))

    report = await stand.service.checks(ANNA, ws.id)

    assert report.state is CiState.awaiting_approval
    assert report.pr_state is PullRequestState.merged
    assert stand.current.ci_status == "awaiting_approval"


# ── кнопка «Официальные паки» ────────────────────────────────────────────────


async def test__info__repository_and_no_workspace_yet() -> None:
    stand = _stand()
    stand.workspaces.items.clear()

    info = await stand.official.info(ANNA)

    assert info.repo is not None
    assert info.repo.url == UPSTREAM
    assert info.workspace_id is None


async def test__info__existing_official_workspace__named() -> None:
    stand = _stand()

    info = await stand.official.info(ANNA)

    assert info.workspace_id == stand.ws.id


async def test__open__existing_official_workspace__returned_not_created() -> None:
    stand = _stand()

    view, created = await stand.official.open(ANNA, uuid4())

    assert created is False
    assert view.workspace.id == stand.ws.id
    assert stand.workspaces.created == []


async def test__open__own_token__creates_partial_clone_of_packs_with_that_credential() -> None:
    stand = _stand()
    stand.workspaces.items.clear()
    credential = uuid4()

    _, created = await stand.official.open(ANNA, credential)

    assert created is True
    (inp,) = stand.workspaces.created
    assert (inp.url, inp.packs_path, inp.base_branch, inp.label) == (UPSTREAM, "packs", "master", OFFICIAL_LABEL)
    assert inp.credential_id == credential
    assert inp.service_access is False


async def test__open__no_official_repository__refused() -> None:
    stand = _stand()
    hidden = OfficialPacks(None, stand.workspaces)  # type: ignore[arg-type]

    with pytest.raises(PackStudioError) as caught:
        await hidden.open(ANNA, uuid4())

    assert caught.value.code is PackStudioErrorCode.official_unavailable
