"""Официальные паки (срез T22): кнопка, доступ бота, согласие с лицензией, лимит, только папка паков.

Сценарий `PackGitService` и `OfficialPacks` на фейках портов: ни git, ни хостинга, ни сети. Push и PR записываются
фейками, по ним проверяется, куда ушла ветка и что видно в PR.
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
    PullRequestRef,
    PullRequestState,
    PushOutcome,
    RepoPermissions,
    WorkGitStatus,
)
from hse_doc_studio.core.pack_studio.official import official_repo
from hse_doc_studio.core.pack_studio.protocols import PackCheckReport, ServiceAccess, VersionNotes
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.use_cases.pack_studio.git import AUDIT_PROPOSED, PackGitService, ProposeInput
from hse_doc_studio.use_cases.pack_studio.official import (
    AUDIT_LICENSE,
    OFFICIAL_LABEL,
    OfficialAccess,
    OfficialPacks,
)
from hse_doc_studio.use_cases.pack_studio.workspaces import WorkspaceView

UPSTREAM = "https://github.com/AlexeyShalaev/hse-doc-studio"
BOT_FORK = "https://github.com/studio-bot/hse-doc-studio.git"
ANNA = Actor.user("u_anna", "Анна Иванова", "anna@real.example.org")
REAL_EMAIL = "anna@real.example.org"
CHANGED = "hse-cs-sse/templates/coursework/versions/2026.1.8/version.yaml"
NOW = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def _bot_access(**changes: Any) -> ServiceAccess:
    base = ServiceAccess(
        id=uuid4(),
        url=UPSTREAM,
        host="github.com",
        port=None,
        repo_key="github.com/alexeyshalaev/hse-doc-studio",
        label="Бот",
        created_at=NOW,
        token_family="ghp",
        fork_mode=True,
    )
    return replace(base, **changes)


def _workspace(**changes: Any) -> PackWorkspace:
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

    async def status(self, _dirs: Any, *, base_branch: str, packs_path: str) -> WorkGitStatus:
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

    async def commit(self, _dirs: Any, *, packs_path: str, message: str, author: VcsAuthor) -> str | None:
        self.authors.append(author)
        self.dirty = False
        return "c" * 40

    async def branch_paths(self, _dirs: Any, *, base_branch: str) -> tuple[str, ...]:
        return self.branch_files

    async def base_registries(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {}

    async def push(self, _dirs: Any, target: RemoteTarget, *, branch: str, push_options: Any = ()) -> PushOutcome:
        self.pushes.append(target)
        return PushOutcome(sha="c" * 40, remote_output="")


@dataclass
class _Hosting:
    can_push: bool | None = False
    pulls: list[dict[str, str]] = field(default_factory=list)
    forks_made: int = 0
    synced: list[str] = field(default_factory=list)
    ci: CiReport | None = None
    pr_state: PullRequestState | None = None

    async def permissions(self, *_args: Any) -> RepoPermissions:
        return RepoPermissions(can_push=self.can_push)

    async def fork(self, _repo: Any, target: RemoteTarget, *, create: bool) -> ForkRef | None:
        assert target.url.display_url.startswith(UPSTREAM), "форк ищется токеном бота по адресу официального"
        self.forks_made += 1
        return ForkRef(path="studio-bot/hse-doc-studio", clone_url=BOT_FORK)

    async def sync_fork(self, fork: Any, _target: RemoteTarget, *, branch: str) -> bool:
        self.synced.append(f"{fork.path}@{branch}")
        return True

    async def open_pull_request(self, _repo: Any, target: RemoteTarget, **kwargs: str) -> PullRequestRef:
        self.pulls.append({**kwargs, "target": target.url.display_url})
        return PullRequestRef(number=412, url=f"{UPSTREAM}/pull/412")

    async def ci_status(self, _repo: Any, _target: Any, *, sha: str, branch: str | None) -> CiReport:
        return self.ci or CiReport(state=CiState.none, sha=sha)

    async def pull_request_state(self, *_args: Any) -> PullRequestState | None:
        return self.pr_state


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


class _Services:
    def __init__(self, access: ServiceAccess | None) -> None:
        self.access = access

    async def get(self, access_id: UUID) -> ServiceAccess | None:
        return self.access if self.access is not None and self.access.id == access_id else None

    async def find(self, _key: str) -> ServiceAccess | None:
        return self.access

    async def set_fork_url(self, access_id: UUID, fork_url: str) -> None:
        assert self.access is not None
        assert access_id == self.access.id
        self.access = replace(self.access, fork_url=fork_url)


class _Settings:
    def __init__(self, enabled: bool | None = None, limit: int | None = None) -> None:
        self.value = (enabled, limit)

    async def get(self) -> tuple[bool | None, int | None]:
        return self.value

    async def set(self, *, enabled: bool, daily_limit: int) -> None:
        self.value = (enabled, daily_limit)


class _Counter:
    def __init__(self, used: int = 0) -> None:
        self.used = used

    async def count_since(self, user_id: str, since: datetime) -> int:
        assert user_id == "u_anna"
        return self.used


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def record(self, action: str, **kwargs: Any) -> None:
        self.events.append((action, kwargs))


class _Access:
    def __init__(self, right: bool = True) -> None:
        self.right = right

    async def has_right(self, _actor: Actor) -> bool:
        return self.right


@dataclass
class _Stand:
    ws: PackWorkspace
    workspaces: _Workspaces
    git: _Git
    hosting: _Hosting
    services: _Services
    audit: _Audit
    official: OfficialPacks
    service: PackGitService

    @property
    def current(self) -> PackWorkspace:
        return self.workspaces.items[self.ws.id]


def _stand(  # noqa: PLR0913 — что меняют тесты
    *,
    access: ServiceAccess | None = None,
    ws: PackWorkspace | None = None,
    settings: _Settings | None = None,
    used: int = 0,
    git: _Git | None = None,
    hosting: _Hosting | None = None,
    right: bool = True,
) -> _Stand:
    bot = _bot_access() if access is None else access
    workspace = ws or _workspace(service_access_id=bot.id)
    workspaces = _Workspaces(workspace)
    services = _Services(bot)
    audit = _Audit()
    repo = official_repo(UPSTREAM, packs_path="packs", base_branch="master", license="Apache-2.0")
    official = OfficialPacks(
        repo,
        workspaces,  # type: ignore[arg-type]
        _Access(right),  # type: ignore[arg-type]
        settings or _Settings(),
        default_daily_limit=5,
        service_access=services,  # type: ignore[arg-type]
        counter=_Counter(used),
        audit=audit,  # type: ignore[arg-type]
    )
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
        noreply_domain="noreply.studio.example.org",
        site_url="https://studio.example.org",
    )
    return _Stand(workspace, workspaces, the_git, the_hosting, services, audit, official, service)


# ── бот: куда уходит ветка и что видно в PR ──────────────────────────────────


async def test__bot__first_proposal__fork_found_by_bot_token_branch_to_fork_pr_into_official() -> None:
    stand = _stand()

    view = await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert [t.url.display_url for t in stand.git.pushes] == [BOT_FORK]
    assert stand.hosting.forks_made == 1
    assert stand.services.access is not None
    assert stand.services.access.fork_url == BOT_FORK
    assert stand.hosting.synced == ["studio-bot/hse-doc-studio@master"]
    (pull,) = stand.hosting.pulls
    assert pull["target"] == UPSTREAM
    assert pull["head"].startswith("studio-bot:pack-studio/")
    assert pull["base"] == "master"
    assert "пользователем Анна Иванова" in pull["body"]
    assert "служебным аккаунтом установки Студии (https://studio.example.org)" in pull["body"]
    assert REAL_EMAIL not in pull["body"]
    assert view.pull_request is not None
    assert view.pushed_to == BOT_FORK


async def test__bot__commit_author__name_from_profile_email_noreply_even_if_real_was_chosen() -> None:
    stand = _stand()

    await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert stand.git.authors == [VcsAuthor(name="Анна Иванова", email="u_anna@noreply.studio.example.org")]


async def test__bot__known_fork__no_fork_call_and_never_pushes_to_official() -> None:
    hosting = _Hosting(can_push=True)
    stand = _stand(access=_bot_access(fork_url=BOT_FORK), hosting=hosting)

    await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert hosting.forks_made == 0
    assert [t.url.display_url for t in stand.git.pushes] == [BOT_FORK]


async def test__bot__proposal__audited_with_bot_flag_for_the_daily_count() -> None:
    stand = _stand()

    await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    proposed = [details for action, details in stand.audit.events if action == AUDIT_PROPOSED]
    assert len(proposed) == 1
    assert proposed[0]["actor_id"] == "u_anna"
    assert proposed[0]["details"]["bot"] is True
    assert proposed[0]["details"]["official"] is True
    assert proposed[0]["details"]["pushed_to"] == BOT_FORK


# ── ограничения пути с ботом ─────────────────────────────────────────────────


async def test__bot__daily_limit_reached__refused_before_any_commit_or_push() -> None:
    stand = _stand(used=5)

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert caught.value.code is PackStudioErrorCode.proposal_limit
    assert caught.value.status == 429  # noqa: PLR2004
    assert caught.value.ctx["limit"] == 5  # noqa: PLR2004
    assert stand.git.authors == []
    assert stand.git.pushes == []


async def test__bot__limit_set_by_admin__applies() -> None:
    stand = _stand(settings=_Settings(limit=2), used=2)

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert caught.value.ctx["limit"] == 2  # noqa: PLR2004


async def test__bot__turned_off_by_admin__refused() -> None:
    stand = _stand(settings=_Settings(enabled=False))

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert caught.value.code is PackStudioErrorCode.official_bot_unavailable
    assert stand.git.pushes == []


async def test__service_access__branch_touches_files_outside_packs__refused() -> None:
    git = _Git(branch_files=(f"packs/{CHANGED}", ".github/workflows/ci.yml"))
    stand = _stand(git=git)

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, stand.ws.id, ProposeInput(accept_license=True))

    assert caught.value.code is PackStudioErrorCode.paths_outside_packs
    assert caught.value.ctx["files"] == [".github/workflows/ci.yml"]
    assert git.pushes == []


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


async def test__own_token_in_official__consent_asked_but_no_bot_rules() -> None:
    ws = _workspace(credential_id=uuid4(), fork_url="https://github.com/anna/hse-doc-studio.git")
    stand = _stand(ws=ws, used=99, git=_Git(branch_files=("README.md",)))

    with pytest.raises(PackStudioError) as caught:
        await stand.service.propose(ANNA, ws.id, ProposeInput())
    await stand.service.propose(ANNA, ws.id, ProposeInput(accept_license=True))

    assert caught.value.code is PackStudioErrorCode.license_consent_required
    assert [t.url.display_url for t in stand.git.pushes] == ["https://github.com/anna/hse-doc-studio.git"]
    assert stand.git.authors[0].email == REAL_EMAIL


async def test__other_repository__no_consent_needed() -> None:
    ws = _workspace(remote_url="https://github.com/acme/packs", credential_id=uuid4())
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


async def test__info__bot_available_with_quota_and_no_workspace_yet() -> None:
    stand = _stand(used=1)
    stand.workspaces.items.clear()

    info = await stand.official.info(ANNA)

    assert info.repo is not None
    assert info.workspace_id is None
    assert info.bot.available is True
    assert info.bot.quota is not None
    assert (info.bot.quota.limit, info.bot.quota.used) == (5, 1)


@pytest.mark.parametrize(
    ("access", "settings", "right", "reason"),
    [
        (_bot_access(fork_mode=False), None, True, "not_configured"),
        (None, _Settings(enabled=False), True, "disabled"),
        (None, None, False, "no_right"),
    ],
)
async def test__info__bot_unavailable_reasons(
    access: ServiceAccess | None, settings: _Settings | None, right: bool, reason: str
) -> None:
    stand = _stand(access=access, settings=settings, right=right)

    info = await stand.official.info(ANNA)

    assert info.bot.available is False
    assert info.bot.reason is not None
    assert info.bot.reason.value == reason


async def test__open__existing_official_workspace__returned_not_created() -> None:
    stand = _stand()

    view, created = await stand.official.open(ANNA, OfficialAccess.bot, None)

    assert created is False
    assert view.workspace.id == stand.ws.id
    assert stand.workspaces.created == []


async def test__open__bot__creates_partial_clone_of_packs_with_service_access() -> None:
    stand = _stand()
    stand.workspaces.items.clear()

    _, created = await stand.official.open(ANNA, OfficialAccess.bot, None)

    assert created is True
    (inp,) = stand.workspaces.created
    assert (inp.url, inp.packs_path, inp.base_branch, inp.label) == (UPSTREAM, "packs", "master", OFFICIAL_LABEL)
    assert inp.service_access is True
    assert inp.credential_id is None


async def test__open__own_token__creates_with_that_credential() -> None:
    stand = _stand()
    stand.workspaces.items.clear()
    credential = uuid4()

    await stand.official.open(ANNA, OfficialAccess.token, credential)

    (inp,) = stand.workspaces.created
    assert inp.credential_id == credential
    assert inp.service_access is False


async def test__open__bot_turned_off__refused() -> None:
    stand = _stand(settings=_Settings(enabled=False))
    stand.workspaces.items.clear()

    with pytest.raises(PackStudioError) as caught:
        await stand.official.open(ANNA, OfficialAccess.bot, None)

    assert caught.value.code is PackStudioErrorCode.official_bot_unavailable
    assert stand.workspaces.created == []


async def test__open__no_official_repository__refused() -> None:
    stand = _stand()
    hidden = OfficialPacks(
        None,
        stand.workspaces,  # type: ignore[arg-type]
        _Access(),  # type: ignore[arg-type]
        None,
        default_daily_limit=5,
    )

    with pytest.raises(PackStudioError) as caught:
        await hidden.open(ANNA, OfficialAccess.token, uuid4())

    assert caught.value.code is PackStudioErrorCode.official_unavailable
