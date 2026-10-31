"""Кто обращается к git по HTTPS и что ему можно в проекте (S16, раздел 7.2).

Принимается только персональный токен доступа: пароль в Basic (имя любое) или Bearer. Cookie и гостевые сессии
git не открывают, токен без git-scope тоже. Права берутся единой политикой без ссылочных прав (S3).
"""

from __future__ import annotations

import base64
import binascii
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Actor, ActorSource, Grant, ProjectAcl
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.entities import GitService
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.entities import ActorCredentials, ApiToken, TokenScope
from hse_doc_studio.core.identity.normalize import hash_token, is_pat
from hse_doc_studio.core.identity.protocols import IActorResolver, IApiTokenRepository, IAuditLog
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

AUTH_REALM = 'Basic realm="HSE Doc Studio"'
_FETCH_AUDIT_EVERY_S = 3600.0
_AUTH_FAIL_AUDIT_EVERY_S = 900.0


class GitHttpErrorKind(StrEnum):
    unauthorized = "unauthorized"
    scope_missing = "scope_missing"
    forbidden = "forbidden"
    not_found = "not_found"


class GitHttpError(Exception):
    """Отказ git-запроса; `message` уже локализован и уходит клиенту текстом (git печатает его как remote:)."""

    def __init__(self, kind: GitHttpErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _unauthorized() -> GitHttpError:
    return GitHttpError(
        GitHttpErrorKind.unauthorized,
        localized_error(
            "Нужен токен с доступом git (Настройки → Токены).",
            "A token with git access is required (Settings → Tokens).",
        ),
    )


def _not_found() -> GitHttpError:
    return GitHttpError(
        GitHttpErrorKind.not_found,
        localized_error("Репозиторий не найден.", "Repository not found."),
    )


@dataclass(frozen=True)
class GitPrincipal:
    actor: Actor
    token: ApiToken

    @property
    def user_id(self) -> str:
        return self.actor.id or ""

    def has(self, scope: TokenScope) -> bool:
        return scope in self.token.scopes


def token_from_headers(headers: Mapping[str, str]) -> str | None:
    """Пароль из `Authorization: Basic` (имя любое) или значение `Bearer`; только формат PAT."""
    raw = headers.get("authorization", "")
    scheme, _, value = raw.partition(" ")
    value = value.strip()
    secret: str | None = None
    if scheme.lower() == "bearer":
        secret = value
    elif scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
        secret = decoded.partition(":")[2]
    if not secret or not is_pat(secret):
        return None
    return secret


class GitHttpAuthenticator:
    def __init__(
        self,
        resolver: IActorResolver,
        tokens: IApiTokenRepository,
        audit: IAuditLog,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resolver = resolver
        self._tokens = tokens
        self._audit = audit
        self._monotonic = monotonic
        # Неудачи по IP с последней записи в журнал: одна реплика api, памяти процесса достаточно.
        self._failures: dict[str, tuple[float, int]] = {}

    async def authenticate(self, headers: Mapping[str, str], ip: str) -> GitPrincipal:
        """Cookie не читаются вовсе: в цепочку резолверов уходит только токен."""
        secret = token_from_headers(headers)
        if secret is None:
            if "authorization" in headers:
                await self._failed(ip)
            raise _unauthorized()
        actor = await self._resolver.resolve(ActorCredentials(bearer_token=secret))
        token = await self._tokens.get_by_hash(hash_token(secret)) if actor is not None else None
        if actor is None or token is None or actor.source is not ActorSource.pat or actor.id != token.user_id:
            await self._failed(ip)
            raise _unauthorized()
        principal = GitPrincipal(actor=actor, token=token)
        if not (principal.has(TokenScope.git_read) or principal.has(TokenScope.git_write)):
            raise GitHttpError(
                GitHttpErrorKind.scope_missing,
                localized_error(
                    "У токена нет доступа к git: нужен scope git:read или git:write.",
                    "The token has no git access: git:read or git:write is required.",
                ),
            )
        return principal

    async def _failed(self, ip: str) -> None:
        """`git.auth_failed` в журнал не чаще раза в 15 минут на адрес, с числом неудач с прошлой записи."""
        now = self._monotonic()
        last, count = self._failures.get(ip, (float("-inf"), 0))
        count += 1
        if now - last < _AUTH_FAIL_AUDIT_EVERY_S:
            self._failures[ip] = (last, count)
            return
        self._failures[ip] = (now, 0)
        horizon = now - _AUTH_FAIL_AUDIT_EVERY_S
        for key in [k for k, (at, _) in self._failures.items() if at < horizon]:
            del self._failures[key]
        await self._audit.record("git.auth_failed", actor_id=None, details={"ip": ip, "count": count})


@dataclass(frozen=True)
class GitAccess:
    principal: GitPrincipal
    project: Project
    acl: ProjectAcl
    grant: Grant
    service: GitService

    @property
    def git_dir(self) -> Path:
        return self.project.folder / ".hse-studio" / "git"

    @property
    def can_push(self) -> bool:
        return self.principal.has(TokenScope.git_write) and decide(self.principal.actor, Action.GIT_PUSH, self.acl) is (
            Decision.allow
        )


class AuthorizeGitServiceUC:
    """Право на сервис git в проекте: выборка по GIT_FETCH, отправка (и её реклама) по GIT_PUSH и git:write."""

    def __init__(
        self,
        acl: IProjectAclRepository,
        project_repo: IProjectRepository,
        project_index: IProjectIndexRepository,
    ) -> None:
        self._acl = acl
        self._projects = GetProjectUC(project_repo, project_index)

    async def execute(self, principal: GitPrincipal, project_id: UUID, service: GitService) -> GitAccess:
        acl = await self._acl.load_for(principal.actor, project_id, include_links=False)
        grant = acl.grant_for(principal.actor) if acl is not None else None
        if acl is None or grant is None:
            raise _not_found()
        push = service is GitService.receive_pack
        action = Action.GIT_PUSH if push else Action.GIT_FETCH
        if decide(principal.actor, action, acl) is not Decision.allow:
            raise GitHttpError(
                GitHttpErrorKind.forbidden,
                localized_error(
                    "У вас нет права отправлять изменения в этот проект."
                    if push
                    else "У вас нет права читать исходники этого проекта.",
                    "You may not push to this project." if push else "You may not read the sources of this project.",
                ),
            )
        if push and not principal.has(TokenScope.git_write):
            raise GitHttpError(
                GitHttpErrorKind.scope_missing,
                localized_error(
                    "Токен только для чтения: для отправки нужен scope git:write.",
                    "The token is read-only: pushing requires the git:write scope.",
                ),
            )
        try:
            project = (await self._projects.execute(GetProjectInput(project_id=project_id))).project
        except NotFoundError:
            raise _not_found() from None
        return GitAccess(principal=principal, project=project, acl=acl, grant=grant, service=service)


class GitFetchAudit:
    """Журнал выборок: память процесса (одна реплика api), иначе каждый `git fetch` писал бы строку."""

    def __init__(self, audit: IAuditLog, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._audit = audit
        self._monotonic = monotonic
        self._fetch_audited: dict[tuple[str, UUID], float] = {}

    async def record_fetch(self, access: GitAccess) -> None:
        """`git.fetch` не чаще раза в час на человека и проект."""
        key = (access.principal.user_id, access.project.id)
        now = self._monotonic()
        last = self._fetch_audited.get(key)
        if last is not None and now - last < _FETCH_AUDIT_EVERY_S:
            return
        for stale in [k for k, at in self._fetch_audited.items() if now - at >= _FETCH_AUDIT_EVERY_S]:
            del self._fetch_audited[stale]
        self._fetch_audited[key] = now
        await self._audit.record(
            "git.fetch", actor_id=access.principal.user_id, target=str(access.project.id), details={}
        )


class GitConcurrency:
    """Сколько запросов git одного человека идут одновременно (MAX_CONCURRENT_PER_USER)."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._running: dict[str, int] = {}

    def try_acquire(self, user_id: str) -> bool:
        current = self._running.get(user_id, 0)
        if current >= self._limit:
            return False
        self._running[user_id] = current + 1
        return True

    def release(self, user_id: str) -> None:
        current = self._running.get(user_id, 0) - 1
        if current <= 0:
            self._running.pop(user_id, None)
        else:
            self._running[user_id] = current
