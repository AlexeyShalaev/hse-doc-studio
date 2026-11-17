"""Git рабочего пространства Студии шаблонов: ветка, коммит, «Предложить изменения», статус CI (срез T6).

docs/design/template-studio.md, 4.2 до 4.4 и раздел 12. Всё идёт под замком пространства (`WorkspaceTasks`): вторая
операция получает `workspace_busy`, как при клоне и выборке.

- Ветка: первая сохранённая правка создаёт рабочую ветку `pack-studio/<человек>/<пак>-<шаблон>-<версия>` на текущей
  вершине (правки на диске остаются); можно назвать свою или перейти на свою прежнюю, в том числе с сервера.
- Коммит: автор и коммиттер из профиля человека (`ICommitAuthorProvider`), сообщение по conventional commits.
- «Предложить изменения»: коммит несохранённого, проверки пака (4.4, тот же код, что `pack check --base`), push
  рабочей ветки, PR GitHub через REST или MR GitLab через push options. Нет права push: форк (указанный или созданный
  токеном на GitHub) и ссылка compare, если API отказал.
- Статус проверок хостинга по отправленной вершине; слияние свежей базы в рабочую ветку; «Начать заново от базы».
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar
from uuid import UUID

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import IGitTransport
from hse_doc_studio.core.git_sync.providers import GitProvider, web_base
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl, parse_remote_url
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.pack_studio.entities import PackWorkspace
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.git_flow import (
    CheckSummary,
    CiReport,
    CiState,
    ForkRef,
    HostingRepo,
    PullRequestRef,
    PullRequestState,
    PushOutcome,
    VersionSummary,
    WorkGitStatus,
    changed_versions,
    compare_url,
    default_commit_message,
    gitlab_push_options,
    merge_request_from_output,
    proposal_body,
    repo_path_of,
    touched_scopes,
    work_branch_name,
)
from hse_doc_studio.core.pack_studio.official import outside_packs
from hse_doc_studio.core.pack_studio.paths import RELEASES_FILE, TEMPLATES_DIR
from hse_doc_studio.core.pack_studio.protocols import (
    IPackChecker,
    IPackHosting,
    IPackWorkspaceGit,
    PackCheckReport,
)
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError
from hse_doc_studio.core.vcs.protocols import ICommitAuthorProvider
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.use_cases.git_sync.provider_resolver import ProviderResolver
from hse_doc_studio.use_cases.pack_studio.official import OfficialPacks
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

logger = structlog.get_logger()
_T = TypeVar("_T")

AUDIT_PROPOSED = "pack_studio.proposed"
_API_SUFFIXES = ("/api/v3", "/api/v4", "/api/v1")
_GITHUB_API = "https://api.github.com"
# Свежий форк GitHub создаётся асинхронно: первая отправка может не найти репозиторий.
_FORK_PUSH_ATTEMPTS = 5
_FORK_PUSH_DELAY_S = 2.0
_MESSAGE_MAX = 2_000
_TITLE_MAX = 200
_DESCRIPTION_MAX = 20_000
_FINDINGS_MAX = 50


@dataclass(frozen=True)
class GitView:
    workspace: PackWorkspace
    status: WorkGitStatus
    provider: GitProvider
    # Ссылка «Открыть PR в браузере», если ветка отправлена, а PR нет.
    compare_url: str | None


@dataclass(frozen=True)
class BranchList:
    """Ветки пространства: текущая, базовая, локальные и (если сервер ответил) отправленные на сервер."""

    current: str | None
    base: str | None
    local: tuple[str, ...]
    server: tuple[str, ...]
    # Сервер не ответил: `server` пуст, а локальные ветки верны.
    server_unavailable: bool = False


@dataclass(frozen=True)
class CommitView:
    git: GitView
    sha: str | None
    committed: bool


@dataclass(frozen=True)
class ForkChoice:
    """Форк для отправки без права push: свой адрес или создать токеном (только GitHub)."""

    url: str | None = None
    create: bool = False


@dataclass(frozen=True)
class ProposeInput:
    title: str | None = None
    description: str | None = None
    message: str | None = None
    fork: ForkChoice | None = None
    # Официальные паки (T22): согласие, что вклад публичен и идёт под лицензией репозитория.
    accept_license: bool = False


@dataclass(frozen=True)
class ProposeView:
    git: GitView
    pushed_sha: str
    pushed_to: str
    pull_request: PullRequestRef | None
    compare_url: str | None
    # Отправлено, но PR открыть не дали (`pr_permission_missing`): человек открывает его по ссылке compare.
    pr_error: PackStudioError | None
    report: PackCheckReport


def _now() -> datetime:
    return datetime.now(UTC)


def _branch_name(raw: str) -> str:
    try:
        return validate_ref_name(raw.strip())
    except VcsInvalidRefError:
        raise PackStudioError(PackStudioErrorCode.branch_name_invalid) from None


def _clip(text: str | None, limit: int) -> str | None:
    cleaned = (text or "").strip()
    return cleaned[:limit] or None


class PackGitService:
    def __init__(  # noqa: PLR0913 — порты сценария
        self,
        workspaces: PackWorkspaceService,
        git: IPackWorkspaceGit,
        transport: IGitTransport,
        hosting: IPackHosting,
        checker: IPackChecker,
        resolver: ProviderResolver,
        author: ICommitAuthorProvider,
        policy: GitSyncPolicy,
        *,
        diff_max_bytes: int,
        audit: IAuditLog | None = None,
        official: OfficialPacks | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._git = git
        self._transport = transport
        self._hosting = hosting
        self._checker = checker
        self._resolver = resolver
        self._author = author
        self._policy = policy
        self._diff_max = diff_max_bytes
        self._audit = audit
        self._official = official

    # ── чтение ───────────────────────────────────────────────────────────────

    async def view(self, actor: Actor, workspace_id: UUID) -> GitView:
        ws = await self._workspaces.git_ready(actor, workspace_id)
        return await self._view(ws)

    async def diff(self, actor: Actor, workspace_id: UUID) -> tuple[str, bool]:
        ws = await self._workspaces.git_ready(actor, workspace_id)
        return await self._locked(
            ws,
            lambda: self._git.diff(
                self._workspaces.dirs_of(ws),
                self._workspaces.target_of(ws),
                base_branch=ws.base_branch or "",
                packs_path=ws.packs_path,
                max_bytes=self._diff_max,
            ),
        )

    async def branches(self, actor: Actor, workspace_id: UUID) -> BranchList:
        """Список веток для «переключить ветку»: локальные и серверные (сервер недоступен: только локальные)."""
        ws = await self._workspaces.git_ready(actor, workspace_id)
        status = await self._status(ws)
        local = await self._git.local_branches(self._workspaces.dirs_of(ws))
        try:
            server = await self._server_branches(ws)
        except (GitSyncError, PackStudioError):
            return BranchList(status.branch, ws.base_branch, tuple(local), (), server_unavailable=True)
        return BranchList(status.branch, ws.base_branch, tuple(local), server)

    async def checks(self, actor: Actor, workspace_id: UUID) -> CiReport:
        ws = await self._workspaces.git_ready(actor, workspace_id)
        if ws.pushed_sha is None:
            return CiReport(state=CiState.none, sha=None)
        target = self._workspaces.target_of(ws)
        repo = await self._hosting_repo(target)
        report = await self._hosting.ci_status(repo, target, sha=ws.pushed_sha, branch=ws.work_branch)
        if ws.pr_number is not None:
            report = replace(report, pr_state=await self._pr_state(repo, target, ws.pr_number))
        current = await self._workspaces.git_ready(actor, workspace_id)
        if current.pushed_sha == ws.pushed_sha and current.ci_status != report.state.value:
            await self._workspaces.save(replace(current, ci_status=report.state.value))
        return report

    # ── ветка и коммит ───────────────────────────────────────────────────────

    async def switch(self, actor: Actor, workspace_id: UUID, name: str | None) -> GitView:
        ws = await self._workspaces.git_ready(actor, workspace_id)

        async def work() -> GitView:
            return await self._view(await self._switch(ws, name))

        return await self._locked(ws, work)

    async def commit(self, actor: Actor, workspace_id: UUID, message: str | None) -> CommitView:
        ws = await self._workspaces.git_ready(actor, workspace_id)

        async def work() -> CommitView:
            current, sha = await self._commit(ws, message)
            return CommitView(git=await self._view(current), sha=sha, committed=sha is not None)

        return await self._locked(ws, work)

    # ── предложение ──────────────────────────────────────────────────────────

    async def propose(self, actor: Actor, workspace_id: UUID, inp: ProposeInput) -> ProposeView:
        ws = await self._workspaces.git_ready(actor, workspace_id)
        return await self._locked(ws, lambda: self._propose(actor, ws, inp))

    async def merge_base(self, actor: Actor, workspace_id: UUID) -> GitView:
        ws = await self._workspaces.git_ready(actor, workspace_id)

        async def work() -> GitView:
            status = await self._status(ws)
            if status.dirty:
                raise PackStudioError(PackStudioErrorCode.workspace_dirty)
            fresh = await self._workspaces.fetch_base(ws)
            base = fresh.base_branch or ""
            outcome = await self._git.merge_base(
                self._workspaces.dirs_of(fresh),
                self._workspaces.target_of(fresh),
                base_branch=base,
                author=self._author.author(),
                message=f"Merge {base} into {status.branch or 'HEAD'}",
            )
            if outcome.conflicts:
                prefix = "" if fresh.packs_path == "." else f"{fresh.packs_path}/"
                files = [name.removeprefix(prefix) for name in outcome.conflicts]
                raise PackStudioError(PackStudioErrorCode.merge_conflict, files=files)
            return await self._view(fresh)

        return await self._locked(ws, work)

    async def start_over(self, actor: Actor, workspace_id: UUID, *, discard: bool) -> GitView:
        """После слияния PR (4.3, шаг 5): дерево на свежую базу без ветки. Несохранённое теряется только с `discard`."""
        ws = await self._workspaces.git_ready(actor, workspace_id)

        async def work() -> GitView:
            if (await self._status(ws)).dirty and not discard:
                raise PackStudioError(PackStudioErrorCode.workspace_dirty)
            fresh = await self._workspaces.fetch_base(ws)
            await self._git.reset_to_base(
                self._workspaces.dirs_of(fresh), self._workspaces.target_of(fresh), base_branch=fresh.base_branch or ""
            )
            cleared = replace(fresh, work_branch=None, pr_url=None, pr_number=None, ci_status=None, pushed_sha=None)
            return await self._view(await self._workspaces.save(cleared))

        return await self._locked(ws, work)

    # ── шаги ─────────────────────────────────────────────────────────────────

    async def _switch(self, ws: PackWorkspace, name: str | None) -> PackWorkspace:
        dirs = self._workspaces.dirs_of(ws)
        status = await self._status(ws)
        local = await self._git.local_branches(dirs)
        wanted = _branch_name(name) if name else None
        if wanted is not None and wanted == status.branch:
            return ws if ws.work_branch == wanted else await self._workspaces.save(replace(ws, work_branch=wanted))
        if wanted is not None and wanted == ws.base_branch:
            # Рабочая ветка не может быть базовой: PR из базы в саму себя не бывает.
            raise PackStudioError(PackStudioErrorCode.branch_name_invalid)
        remote = await self._server_branches(ws) if wanted not in local else ()
        if wanted is None:
            wanted = self._auto_branch(status, (*local, *remote))
            await self._git.create_branch(dirs, name=wanted)
        elif wanted in local or wanted in remote:
            if status.dirty:
                raise PackStudioError(PackStudioErrorCode.workspace_dirty)
            fetch = wanted not in local
            await self._git.switch_branch(dirs, self._workspaces.target_of(ws), name=wanted, fetch=fetch)
        else:
            await self._git.create_branch(dirs, name=wanted)
        # PR и статус проверок принадлежат ветке: на другой ветке их ищут заново при предложении.
        moved = replace(ws, work_branch=wanted, pr_url=None, pr_number=None, ci_status=None, pushed_sha=None)
        return await self._workspaces.save(moved)

    async def _commit(self, ws: PackWorkspace, message: str | None) -> tuple[PackWorkspace, str | None]:
        status = await self._status(ws)
        if not status.dirty:
            return ws, None
        if status.branch is None:
            ws = await self._switch(ws, None)
        text = _clip(message, _MESSAGE_MAX)
        if text is None:
            # Класс версии для conventional commits (fix для patch, feat для остального): классификатор без базы.
            root = self._workspaces.packs_root(ws)
            report = await asyncio.to_thread(self._checker.check, root, touched_scopes(status.changed), {})
            text = default_commit_message(self._summaries(ws, status, report))
        sha = await self._git.commit(
            self._workspaces.dirs_of(ws),
            self._workspaces.target_of(ws),
            packs_path=ws.packs_path,
            message=text,
            author=self._author.author(),
        )
        return ws, sha

    async def _propose(self, actor: Actor, ws: PackWorkspace, inp: ProposeInput) -> ProposeView:
        official = self._official is not None and self._official.is_official(ws)
        if self._official is not None:
            # Согласие до любых коммитов и сети: отказ ничего не меняет в пространстве.
            ws = await self._official.accept_license(actor, ws, accepted=inp.accept_license)
        ws, _ = await self._commit(ws, inp.message)
        status = await self._status(ws)
        if not status.changed and status.ahead == 0:
            raise PackStudioError(PackStudioErrorCode.nothing_to_propose)
        if status.branch is None:
            ws = await self._switch(ws, None)
            status = await self._status(ws)
        if official or ws.service_access_id is not None:
            await self._require_packs_only(ws)
        report = await self._gate(ws, status)
        branch = status.branch or ""
        base = ws.base_branch or ""
        target = self._workspaces.target_of(ws)
        repo = await self._hosting_repo(target)
        summaries = self._summaries(ws, status, report)
        title = _clip(inp.title, _TITLE_MAX) or default_commit_message(summaries)
        body = proposal_body(
            summaries,
            CheckSummary(errors=report.errors, warnings=report.warnings),
            proposed_by=self._author.author().name,
            extra=_clip(inp.description, _DESCRIPTION_MAX),
        )
        ws, push_target, fork = await self._push_target(ws, target, repo, inp.fork)
        options = (
            gitlab_push_options(target_branch=base, title=title, description=body)
            if repo.provider is GitProvider.gitlab and fork is None
            else []
        )
        pushed = await self._push(
            ws, push_target, repo, branch, options, fresh_fork=fork is not None and inp.fork is not None
        )
        pull, pr_error = await self._pull_request(repo, target, pushed.remote_output, fork, branch, base, title, body)
        link = None if pull is not None else compare_url(repo, base=base, branch=branch, fork=fork)
        saved = await self._workspaces.save(
            replace(
                ws,
                work_branch=branch,
                pushed_sha=pushed.sha,
                pr_url=pull.url if pull else ws.pr_url,
                pr_number=pull.number if pull else ws.pr_number,
                ci_status=CiState.pending.value if pull else None,
                fork_url=fork.clone_url if fork else ws.fork_url,
            )
        )
        await self._record(actor, saved, pull, push_target, official=official)
        return ProposeView(
            git=await self._view(saved),
            pushed_sha=pushed.sha,
            pushed_to=push_target.url.display_url,
            pull_request=pull,
            compare_url=link,
            pr_error=pr_error,
            report=report,
        )

    async def _gate(self, ws: PackWorkspace, status: WorkGitStatus) -> PackCheckReport:
        """Проверки пака перед отправкой (4.4): ошибки не дают предложить, предупреждения идут в описание PR."""
        root = self._workspaces.packs_root(ws)
        scopes = touched_scopes(status.changed)
        templates = await asyncio.to_thread(_template_dirs, root, scopes)
        prefix = "" if ws.packs_path == "." else f"{ws.packs_path}/"
        texts = await self._git.base_registries(
            self._workspaces.dirs_of(ws),
            self._workspaces.target_of(ws),
            base_branch=ws.base_branch or "",
            paths=[f"{prefix}{template}/{RELEASES_FILE}" for template in templates],
        )
        registries = {path[len(prefix) :].removesuffix(f"/{RELEASES_FILE}"): text for path, text in texts.items()}
        report = await asyncio.to_thread(self._checker.check, root, scopes, registries)
        if not report.ok:
            raise PackStudioError(
                PackStudioErrorCode.lint_failed,
                errors=report.errors,
                warnings=report.warnings,
                findings=[
                    {"severity": f.severity, "check": f.check, "path": f.path, "message": f.message}
                    for f in report.findings
                    if f.severity == "error"
                ][:_FINDINGS_MAX],
            )
        return report

    async def _push_target(
        self, ws: PackWorkspace, target: RemoteTarget, repo: HostingRepo, choice: ForkChoice | None
    ) -> tuple[PackWorkspace, RemoteTarget, ForkRef | None]:
        """Куда отправлять: форк пространства, новый форк по выбору человека или сам репозиторий."""
        if choice is not None:
            fork = await self._fork_of(ws, target, repo, choice)
            return ws, self._fork_target(target, fork.clone_url), fork
        if ws.fork_url is not None:
            fork = ForkRef(path=repo_path_of(ws.fork_url, repo.web_base), clone_url=ws.fork_url)
            return ws, self._fork_target(target, ws.fork_url), fork
        if repo.provider in {GitProvider.github, GitProvider.gitlab}:
            permissions = await self._hosting.permissions(repo, target)
            if permissions.can_push is False:
                self._raise_fork_required(ws, repo)
        return ws, target, None

    async def _fork_of(self, ws: PackWorkspace, target: RemoteTarget, repo: HostingRepo, choice: ForkChoice) -> ForkRef:
        if ws.service_access_id is not None:
            # Служебный доступ ходит только в свой репозиторий; у методиста без аккаунта форка нет.
            raise PackStudioError(PackStudioErrorCode.push_denied)
        if choice.url:
            url = self._parse(choice.url)
            if (url.host or "").lower() != (target.url.host or "").lower() or url.kind is not target.url.kind:
                raise PackStudioError(PackStudioErrorCode.fork_required, reason="fork_host_mismatch")
            return ForkRef(path=repo_path_of(url.display_url, repo.web_base), clone_url=url.display_url)
        fork = await self._hosting.fork(repo, target, create=choice.create)
        if fork is None:
            raise PackStudioError(PackStudioErrorCode.fork_required, reason="fork_unavailable")
        return fork

    async def _push(  # noqa: PLR0913 — куда, что и как отправлять
        self,
        ws: PackWorkspace,
        target: RemoteTarget,
        repo: HostingRepo,
        branch: str,
        options: Sequence[str],
        *,
        fresh_fork: bool,
    ) -> PushOutcome:
        dirs = self._workspaces.dirs_of(ws)
        attempts = _FORK_PUSH_ATTEMPTS if fresh_fork else 1
        for attempt in range(attempts):
            try:
                return await self._git.push(dirs, target, branch=branch, push_options=options)
            except GitSyncError as exc:
                if exc.code is GitErrorCode.not_found_or_no_access and attempt + 1 < attempts:
                    await asyncio.sleep(_FORK_PUSH_DELAY_S)
                    continue
                if exc.code is GitErrorCode.forbidden_write:
                    if target.url.display_url != ws.remote_url or ws.service_access_id is not None:
                        raise PackStudioError(PackStudioErrorCode.push_denied) from None
                    self._raise_fork_required(ws, repo)
                raise
        raise AssertionError("unreachable")  # pragma: no cover

    async def _pull_request(  # noqa: PLR0913 — шаги одного PR
        self,
        repo: HostingRepo,
        target: RemoteTarget,
        push_output: str,
        fork: ForkRef | None,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> tuple[PullRequestRef | None, PackStudioError | None]:
        if repo.provider is GitProvider.gitlab:
            if fork is None and (found := merge_request_from_output(push_output)) is not None:
                return found, None
            return None, None
        if repo.provider is not GitProvider.github:
            return None, None
        owner = fork.path.split("/", 1)[0] if fork is not None else repo.owner
        try:
            pull = await self._hosting.open_pull_request(
                repo, target, head=f"{owner}:{branch}", base=base, title=title, body=body
            )
        except PackStudioError as exc:
            if exc.code is PackStudioErrorCode.pr_permission_missing:
                return None, exc
            raise
        return pull, None

    # ── официальные паки (срез T22) ──────────────────────────────────────────

    async def _require_packs_only(self, ws: PackWorkspace) -> None:
        """Официальное пространство и служебный доступ предлагают только паки: коммиты ветки не трогают ничего вне
        папки паков (раздел 9)."""
        paths = await self._git.branch_paths(self._workspaces.dirs_of(ws), base_branch=ws.base_branch or "")
        outside = outside_packs(paths, ws.packs_path)
        if outside:
            raise PackStudioError(PackStudioErrorCode.paths_outside_packs, files=list(outside[:_FINDINGS_MAX]))

    async def _pr_state(self, repo: HostingRepo, target: RemoteTarget, number: int) -> PullRequestState | None:
        try:
            return await self._hosting.pull_request_state(repo, target, number)
        except GitSyncError:
            return None

    # ── служебное ────────────────────────────────────────────────────────────

    async def _locked(self, ws: PackWorkspace, work: Callable[[], Awaitable[_T]]) -> _T:
        return await self._workspaces.tasks.exclusive(ws.id, work)

    async def _status(self, ws: PackWorkspace) -> WorkGitStatus:
        return await self._git.status(
            self._workspaces.dirs_of(ws),
            self._workspaces.target_of(ws),
            base_branch=ws.base_branch or "",
            packs_path=ws.packs_path,
        )

    async def _view(self, ws: PackWorkspace) -> GitView:
        status = await self._status(ws)
        info = await self._resolver.known(*self._host_port(ws))
        link = None
        if ws.pushed_sha is not None and ws.pr_url is None and status.branch is not None:
            repo = self._known_repo(ws, info.id)
            fork = ForkRef(repo_path_of(ws.fork_url, repo.web_base), ws.fork_url) if ws.fork_url else None
            link = compare_url(repo, base=ws.base_branch or "", branch=status.branch, fork=fork)
        return GitView(workspace=ws, status=status, provider=info.id, compare_url=link)

    def _host_port(self, ws: PackWorkspace) -> tuple[str | None, int | None]:
        url = self._workspaces.target_of(ws).url
        return url.host, url.port

    def _known_repo(self, ws: PackWorkspace, provider: GitProvider) -> HostingRepo:
        url = self._workspaces.target_of(ws).url
        base = _site_base(url, None)
        return HostingRepo(provider=provider, path=repo_path_of(url.display_url, base), web_base=base, api_base=None)

    async def _hosting_repo(self, target: RemoteTarget) -> HostingRepo:
        return await hosting_repo_for(self._resolver, target)

    async def _server_branches(self, ws: PackWorkspace) -> tuple[str, ...]:
        probe = await self._transport.probe(self._workspaces.target_of(ws))
        return tuple(probe.branches)

    def _auto_branch(self, status: WorkGitStatus, taken: Sequence[str]) -> str:
        author = self._author.author()
        who = author.email.split("@", 1)[0] if author.email else author.name
        return work_branch_name(who, changed_versions(status.changed), _now(), taken)

    def _summaries(
        self, ws: PackWorkspace, status: WorkGitStatus, report: PackCheckReport | None
    ) -> list[VersionSummary]:
        root = self._workspaces.packs_root(ws)
        classes = {info.path: info for info in report.classes} if report is not None else {}
        summaries: list[VersionSummary] = []
        for ref in changed_versions(status.changed):
            info = classes.get(ref.dir)
            notes = self._checker.notes(root, ref.dir) if report is not None else None
            summaries.append(
                VersionSummary(
                    ref=ref,
                    released_base=info.base if info else None,
                    minimum=info.minimum if info else None,
                    suggested=info.suggested if info else None,
                    by_number=info.by_number if info else None,
                    headline=info.headline if info else {},
                    reasons=info.reasons if info else (),
                    changes=notes.changes if notes else {},
                )
            )
        return summaries

    def _fork_target(self, upstream: RemoteTarget, url: str) -> RemoteTarget:
        parsed = self._parse(url)
        return RemoteTarget(url=parsed, credential_id=upstream.credential_id, insecure_http=upstream.insecure_http)

    def _parse(self, raw: str) -> RemoteUrl:
        return parse_remote_url(
            raw, allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )

    @staticmethod
    def _raise_fork_required(ws: PackWorkspace, repo: HostingRepo) -> None:
        if ws.service_access_id is not None or repo.provider not in {GitProvider.github, GitProvider.gitlab}:
            raise PackStudioError(PackStudioErrorCode.push_denied)
        can_create = repo.provider is GitProvider.github
        raise PackStudioError(PackStudioErrorCode.fork_required, can_create=can_create)

    async def _record(
        self, actor: Actor, ws: PackWorkspace, pull: PullRequestRef | None, pushed_to: RemoteTarget, *, official: bool
    ) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            AUDIT_PROPOSED,
            actor_id=actor.id,
            target=str(ws.id),
            details={
                "url": ws.remote_url,
                "pushed_to": pushed_to.url.display_url,
                "branch": ws.work_branch,
                "sha": ws.pushed_sha,
                "pr_url": pull.url if pull else None,
                "service_access": ws.service_access_id is not None,
                # Срез T22: предложение в официальные паки.
                "official": official,
            },
        )


async def hosting_repo_for(resolver: ProviderResolver, target: RemoteTarget) -> HostingRepo:
    """Репозиторий у хостинга по адресу цели: провайдер, путь, корни сайта и API (с путём установки)."""
    resolved = await resolver.resolve(target.url)
    base = _site_base(target.url, resolved.api_base)
    return HostingRepo(
        provider=resolved.info.id,
        path=repo_path_of(target.url.display_url, base),
        web_base=base,
        api_base=resolved.api_base,
        ca_file=resolved.ca_file,
    )


def _site_base(url: RemoteUrl, api_base: str | None) -> str | None:
    """Корень сайта хостинга: из корня API (с путём установки) или по хосту адреса."""
    if api_base is not None:
        if api_base.rstrip("/") == _GITHUB_API:
            return "https://github.com"
        for suffix in _API_SUFFIXES:
            if api_base.endswith(suffix):
                return api_base[: -len(suffix)]
    if url.kind not in {RemoteKind.https, RemoteKind.http}:
        return web_base(host=url.host, port=None) if url.host else None
    return web_base(host=url.host, port=url.port, secure=url.kind is RemoteKind.https)


def _template_dirs(root: Path, scopes: Sequence[str]) -> list[str]:
    """Каталоги шаблонов под тронутыми каталогами (пак целиком или один шаблон) от папки паков."""
    found: dict[str, None] = {}
    for scope in scopes:
        parts = scope.split("/")
        if len(parts) >= 3:  # noqa: PLR2004
            found.setdefault(scope)
            continue
        templates = root / scope / TEMPLATES_DIR
        if templates.is_dir():
            for child in sorted(templates.iterdir()):
                if child.is_dir() and not child.is_symlink():
                    found.setdefault(f"{scope}/{TEMPLATES_DIR}/{child.name}")
    return list(found)
