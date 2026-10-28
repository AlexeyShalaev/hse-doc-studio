"""Проверка адреса удалённого репозитория до подключения: достижим ли, пустой ли, лежит ли там проект Студии.

В проект ничего не пишется. Сеть и отказ доступа дают ответ `ok=false` с кодом, а не ошибку запроса: человек
правит адрес или доступ прямо в окне подключения. Токен в адресе отбрасывается и нигде не сохраняется.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.git_sync.entities import (
    GitCredential,
    GitCredentialKind,
    GitHostKey,
    GitOperationError,
    ProbeRelation,
    RemoteProbe,
    RemoteTarget,
    SchemaAccess,
    TlsCertificate,
    TokenInfo,
    TokenState,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import DEFAULT_REMOTE_BRANCH, GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitTransport
from hse_doc_studio.core.git_sync.providers import ProviderInfo
from hse_doc_studio.core.git_sync.remote_project import (
    PROJECT_FILE,
    RemoteProject,
    parse_remote_project,
    remote_required_studio,
    remote_schema_access,
)
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl, parse_remote_url
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.use_cases.git_sync.provider_resolver import ProviderResolver, ResolvedProvider
from hse_doc_studio.use_cases.git_sync.token_check import TokenCheck, TokenChecker
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class ProbeInput:
    url: str
    credential_id: UUID | None = None
    project_id: UUID | None = None
    branch: str | None = None
    # Согласие человека на открытый http для этого адреса; политика сервера его не заменяет.
    insecure_http: bool = False


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
    provider: ProviderInfo
    error: GitOperationError | None = None
    host_keys: tuple[GitHostKey, ...] = ()
    certificate: TlsCertificate | None = None
    expected_fingerprint: str | None = None
    actual_fingerprint: str | None = None
    token_info: TokenInfo | None = None
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


def valid_branch(name: str) -> str:
    """Имя ветки без недопустимых для git символов; ошибка идёт как ValueError, API отвечает по ней 422."""
    try:
        return validate_ref_name(name)
    except VcsInvalidRefError as exc:
        raise ValueError(str(exc)) from exc


def require_http_consent(url: RemoteUrl, *, insecure_http: bool) -> None:
    """Открытый http без согласия человека отвергается до любого обращения к серверу: токен по нему ушёл бы открыто.

    Политика сервера лишь разрешает такие адреса, а согласие даёт человек для каждого адреса отдельно (как у
    подключения); без него и проверка адреса, и запрос к API хостинга с токеном не выполняются.
    """
    if url.kind is RemoteKind.http and not insecure_http:
        raise git_error(GitErrorCode.url_scheme_forbidden)


def raise_probe_error(probe: RemoteProbe) -> None:
    """Превращает неудачную проверку в ошибку с кодом; ключи сервера едут в теле для окна подтверждения."""
    if probe.ok:
        return
    error = probe.error or GitOperationError(GitErrorCode.git_error, "")
    ctx: dict[str, object] = {}
    if probe.host_keys:
        ctx["host_keys"] = probe.host_keys
    if probe.certificate is not None:
        ctx["certificate"] = probe.certificate
    if probe.expected_fingerprint is not None:
        ctx["expected"] = probe.expected_fingerprint
        ctx["actual"] = probe.actual_fingerprint
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
        resolver: ProviderResolver,
        token_checker: TokenChecker,
        access: IProjectAccessChecker,
    ) -> None:
        self._get_project = GetProjectUC(project_repo, project_index_repo)
        self._access = access
        self._transport = transport
        self._credentials = credentials
        self._templates = template_repo
        self._policy = policy
        self._resolver = resolver
        self._tokens = token_checker

    async def execute(self, inp: ProbeInput) -> ProbeView:
        self._policy.require_enabled()
        url = parse_remote_url(
            inp.url, allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        require_http_consent(url, insecure_http=inp.insecure_http)
        credential = self._credentials.get(inp.credential_id) if inp.credential_id is not None else None
        if inp.credential_id is not None and credential is None:
            raise git_error(GitErrorCode.credentials_missing)
        local_id = None
        if inp.project_id is not None:
            await self._access.require(inp.project_id, Action.PROJECT_SETTINGS)
            local_id = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project.id
        # Открытый http сюда доходит только с согласием человека (`require_http_consent`).
        target = RemoteTarget(url, inp.credential_id, insecure_http=url.kind is RemoteKind.http)
        resolved = await self._resolver.resolve(url)
        token = await self._check_token(url, credential, resolved)
        if token is not None and token.state in {TokenState.expired, TokenState.rejected}:
            return self._rejected_token(url, resolved, token.state, token.info)
        ctx = _Context(resolved.info, token.info if token else None)
        probe = await self._transport.probe(target)
        if not probe.ok:
            return self._failed(url, ctx, probe)
        if probe.empty:
            return self._view(url, ctx, probe, ProbeRelation.empty)
        return await self._inspect_tip(url, ctx, target, probe, inp.branch, local_id)

    async def _check_token(
        self, url: RemoteUrl, credential: GitCredential | None, resolved: ResolvedProvider
    ) -> TokenCheck | None:
        """Токен спрашивают у сервера, только если он создан для этого хоста: чужому серверу токен не уходит."""
        if (
            credential is None
            or credential.kind is not GitCredentialKind.pat
            or url.kind not in {RemoteKind.https, RemoteKind.http}
            or credential.host != url.host
        ):
            return None
        try:
            return await self._tokens.check(credential, resolved)
        except GitSyncError:
            # Спросить не вышло (связь, сертификат): причину назовёт проверка git ниже.
            return None

    def _rejected_token(
        self, url: RemoteUrl, resolved: ResolvedProvider, state: TokenState, info: TokenInfo | None
    ) -> ProbeView:
        code = GitErrorCode.token_expired if state is TokenState.expired else GitErrorCode.auth_failed
        error = git_error(code)
        return ProbeView(
            ok=False,
            url=url,
            reachable=True,
            auth_ok=False,
            empty=False,
            default_branch=None,
            branches=(),
            relation=ProbeRelation.unknown,
            provider=resolved.info,
            error=GitOperationError(error.code, error.detail),
            token_info=info,
        )

    async def _inspect_tip(
        self,
        url: RemoteUrl,
        ctx: _Context,
        target: RemoteTarget,
        probe: RemoteProbe,
        requested: str | None,
        local_id: UUID | None,
    ) -> ProbeView:
        branch = choose_remote_branch(requested, probe)
        if branch not in probe.branches:
            return self._failed(url, ctx, _branch_missing(probe))
        try:
            raw = await self._transport.read_tip_file(target, branch=branch, path=PROJECT_FILE)
        except GitSyncError as exc:
            return self._failed(url, ctx, _failure(probe, exc))
        return self._describe(url, ctx, probe, raw, local_id)

    def _describe(
        self, url: RemoteUrl, ctx: _Context, probe: RemoteProbe, raw: bytes | None, local_id: UUID | None
    ) -> ProbeView:
        if raw is None:
            return self._view(url, ctx, probe, ProbeRelation.not_studio_project)
        project = parse_remote_project(raw)
        if project is None:
            return self._view(url, ctx, probe, ProbeRelation.unknown)
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
            ctx,
            probe,
            relation,
            project=project,
            schema_access=remote_schema_access(project.schema),
            required_studio=remote_required_studio(project, template_available=template_available),
            template_available=template_available,
        )

    @staticmethod
    def _failed(url: RemoteUrl, ctx: _Context, probe: RemoteProbe) -> ProbeView:
        return ProbeView(
            ok=False,
            url=url,
            reachable=probe.reachable,
            auth_ok=probe.auth_ok,
            empty=False,
            default_branch=probe.default_branch,
            branches=probe.branches,
            relation=ProbeRelation.unknown,
            provider=ctx.provider,
            error=probe.error,
            host_keys=probe.host_keys,
            certificate=probe.certificate,
            expected_fingerprint=probe.expected_fingerprint,
            actual_fingerprint=probe.actual_fingerprint,
            token_info=ctx.token_info,
        )

    @staticmethod
    def _view(
        url: RemoteUrl,
        ctx: _Context,
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
            provider=ctx.provider,
            token_info=ctx.token_info,
            project=project,
            schema_access=schema_access,
            required_studio=required_studio,
            template_available=template_available,
        )


@dataclass(frozen=True)
class _Context:
    """Что известно до проверки git и попадает в любой ответ: провайдер и итог проверки токена."""

    provider: ProviderInfo
    token_info: TokenInfo | None


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
    reachable = exc.code not in {
        GitErrorCode.offline,
        GitErrorCode.timeout,
        GitErrorCode.tls_error,
        GitErrorCode.tls_untrusted_ca,
        GitErrorCode.tls_pin_mismatch,
    }
    return RemoteProbe(
        ok=False,
        reachable=reachable,
        auth_ok=exc.code not in {GitErrorCode.auth_failed, GitErrorCode.credentials_missing},
        default_branch=probe.default_branch,
        branches=probe.branches,
        error=GitOperationError(exc.code, exc.detail),
        host_keys=_host_keys(exc),
        certificate=_certificate(exc),
        expected_fingerprint=_text(exc.ctx.get("expected")),
        actual_fingerprint=_text(exc.ctx.get("actual")),
    )


def _host_keys(exc: GitSyncError) -> tuple[GitHostKey, ...]:
    keys = exc.ctx.get("host_keys")
    return tuple(keys) if isinstance(keys, tuple) else ()


def _certificate(exc: GitSyncError) -> TlsCertificate | None:
    certificate = exc.ctx.get("certificate")
    return certificate if isinstance(certificate, TlsCertificate) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None
