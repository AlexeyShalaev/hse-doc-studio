"""Проверка адреса удалённого репозитория до подключения: достижим ли, пустой ли, лежит ли там проект Студии.

В проект ничего не пишется. Сеть и отказ доступа дают ответ `ok=false` с кодом, а не ошибку запроса: человек
правит адрес или доступ прямо в окне подключения. Токен в адресе отбрасывается и нигде не сохраняется.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import (
    GitHostKey,
    GitOperationError,
    ProbeRelation,
    RemoteProbe,
    RemoteTarget,
    SchemaAccess,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import DEFAULT_REMOTE_BRANCH, GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitTransport
from hse_doc_studio.core.git_sync.remote_project import (
    PROJECT_FILE,
    RemoteProject,
    parse_remote_project,
    remote_required_studio,
    remote_schema_access,
)
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl, parse_remote_url
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class ProbeInput:
    url: str
    credential_id: UUID | None = None
    project_id: UUID | None = None
    branch: str | None = None


@dataclass(frozen=True)
class ProbeView:
    ok: bool
    url: RemoteUrl
    reachable: bool
    auth_ok: bool
    empty: bool
    default_branch: str | None
    branches: tuple[str, ...]
    relation: ProbeRelation
    error: GitOperationError | None = None
    host_keys: tuple[GitHostKey, ...] = ()
    project: RemoteProject | None = None
    schema_access: SchemaAccess | None = None
    required_studio: str | None = None
    template_available: bool | None = None


def choose_remote_branch(requested: str | None, probe: RemoteProbe) -> str:
    """Ветка на сервере: названная человеком, иначе ветка по умолчанию, иначе main или первая из существующих."""
    if requested:
        return requested
    if probe.default_branch:
        return probe.default_branch
    if not probe.branches or DEFAULT_REMOTE_BRANCH in probe.branches:
        return DEFAULT_REMOTE_BRANCH
    return sorted(probe.branches)[0]


def raise_probe_error(probe: RemoteProbe) -> None:
    """Превращает неудачную проверку в ошибку с кодом; ключи сервера едут в теле для окна подтверждения."""
    if probe.ok:
        return
    error = probe.error or GitOperationError(GitErrorCode.git_error, "")
    ctx: dict[str, object] = {"host_keys": probe.host_keys} if probe.host_keys else {}
    raise GitSyncError(error.code, error.detail, **ctx)


class ProbeRemoteUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        transport: IGitTransport,
        credentials: IGitCredentialRepository,
        template_repo: ITemplateRepository,
        policy: GitSyncPolicy,
    ) -> None:
        self._get_project = GetProjectUC(project_repo, project_index_repo)
        self._transport = transport
        self._credentials = credentials
        self._templates = template_repo
        self._policy = policy

    async def execute(self, inp: ProbeInput) -> ProbeView:
        if not self._policy.enabled:
            raise git_error(GitErrorCode.git_unavailable)
        url = parse_remote_url(
            inp.url, allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        if inp.credential_id is not None and self._credentials.get(inp.credential_id) is None:
            raise git_error(GitErrorCode.credentials_missing)
        local_id = None
        if inp.project_id is not None:
            local_id = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project.id
        # Открытый http проверяется как разрешённый: согласие на него человек даёт при подключении.
        target = RemoteTarget(url, inp.credential_id, insecure_http=url.kind is RemoteKind.http)
        probe = await self._transport.probe(target)
        if not probe.ok:
            return self._failed(url, probe)
        if probe.empty:
            return self._view(url, probe, ProbeRelation.empty)
        return await self._inspect_tip(url, target, probe, inp.branch, local_id)

    async def _inspect_tip(
        self, url: RemoteUrl, target: RemoteTarget, probe: RemoteProbe, requested: str | None, local_id: UUID | None
    ) -> ProbeView:
        branch = choose_remote_branch(requested, probe)
        if branch not in probe.branches:
            return self._failed(url, _branch_missing(probe))
        try:
            raw = await self._transport.read_tip_file(target, branch=branch, path=PROJECT_FILE)
        except GitSyncError as exc:
            return self._failed(url, _failure(probe, exc))
        return self._describe(url, probe, raw, local_id)

    def _describe(self, url: RemoteUrl, probe: RemoteProbe, raw: bytes | None, local_id: UUID | None) -> ProbeView:
        if raw is None:
            return self._view(url, probe, ProbeRelation.not_studio_project)
        project = parse_remote_project(raw)
        if project is None:
            return self._view(url, probe, ProbeRelation.unknown)
        template_available = (
            self._templates.get_version(project.pack_id, project.template_id, project.template_version) is not None
        )
        # Общая ли у проектов история, выясняет подключение: для этого нужна полная выборка, а не проверка.
        if local_id is None:
            relation = ProbeRelation.studio_project
        else:
            relation = ProbeRelation.same_project if project.id == local_id else ProbeRelation.other_project
        return self._view(
            url,
            probe,
            relation,
            project=project,
            schema_access=remote_schema_access(project.schema),
            required_studio=remote_required_studio(project, template_available=template_available),
            template_available=template_available,
        )

    @staticmethod
    def _failed(url: RemoteUrl, probe: RemoteProbe) -> ProbeView:
        return ProbeView(
            ok=False,
            url=url,
            reachable=probe.reachable,
            auth_ok=probe.auth_ok,
            empty=False,
            default_branch=probe.default_branch,
            branches=probe.branches,
            relation=ProbeRelation.unknown,
            error=probe.error,
            host_keys=probe.host_keys,
        )

    @staticmethod
    def _view(
        url: RemoteUrl,
        probe: RemoteProbe,
        relation: ProbeRelation,
        *,
        project: RemoteProject | None = None,
        schema_access: SchemaAccess | None = None,
        required_studio: str | None = None,
        template_available: bool | None = None,
    ) -> ProbeView:
        return ProbeView(
            ok=True,
            url=url,
            reachable=True,
            auth_ok=True,
            empty=probe.empty,
            default_branch=probe.default_branch,
            branches=probe.branches,
            relation=relation,
            project=project,
            schema_access=schema_access,
            required_studio=required_studio,
            template_available=template_available,
        )


def _branch_missing(probe: RemoteProbe) -> RemoteProbe:
    error = git_error(GitErrorCode.branch_missing)
    return RemoteProbe(
        ok=False,
        reachable=True,
        auth_ok=True,
        default_branch=probe.default_branch,
        branches=probe.branches,
        error=GitOperationError(error.code, error.detail),
    )


def _failure(probe: RemoteProbe, exc: GitSyncError) -> RemoteProbe:
    reachable = exc.code not in {GitErrorCode.offline, GitErrorCode.timeout, GitErrorCode.tls_error}
    return RemoteProbe(
        ok=False,
        reachable=reachable,
        auth_ok=exc.code not in {GitErrorCode.auth_failed, GitErrorCode.credentials_missing},
        default_branch=probe.default_branch,
        branches=probe.branches,
        error=GitOperationError(exc.code, exc.detail),
        host_keys=_host_keys(exc),
    )


def _host_keys(exc: GitSyncError) -> tuple[GitHostKey, ...]:
    keys = exc.ctx.get("host_keys")
    return tuple(keys) if isinstance(keys, tuple) else ()
