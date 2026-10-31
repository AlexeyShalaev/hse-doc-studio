"""Сервер HSE Doc Studio как git-remote локальной Студии: вход по коду устройства, список серверов и проектов.

Вход идёт фоновой задачей локального api: она опрашивает `/auth/device/token` с интервалом сервера (и `slow_down`),
а получив токен, сохраняет его обычным доступом (`pat`, имя `hse`, метка «HSE Doc Studio · host», origin device).
Состояние входа живёт в памяти процесса до 15 минут. Токен на сервере человек отзывает на сайте.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.client import (
    IStudioServerClient,
    StudioProjectPage,
    StudioServerError,
    StudioServerErrorCode,
    StudioServerTarget,
)
from hse_doc_studio.core.git_sync.credentials import token_family
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitHostSettingsRepository
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error

logger = structlog.get_logger()

DEVICE_ORIGIN = "device"
STUDIO_USERNAME = "hse"
_KEEP_S = 15 * 60
_SLOW_DOWN_S = 5
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


class LoginState:
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"
    error = "error"


@dataclass(frozen=True)
class StudioServerLogin:
    login_id: str
    server_url: str
    state: str
    user_code: str | None = None
    verification_uri_complete: str | None = None
    expires_at: datetime | None = None
    credential_id: UUID | None = None
    code: str | None = None


@dataclass(frozen=True)
class StudioServerItem:
    credential_id: UUID
    server_url: str
    host: str
    account_name: str | None
    scopes: tuple[str, ...]
    expires_at: datetime | None
    state: str


def server_url_of(credential: GitCredential) -> str:
    """Корень сервера по доступу: по http ходим только к своему компьютеру, иначе https."""
    scheme = "http" if credential.host in _LOOPBACK else "https"
    port = f":{credential.port}" if credential.port else ""
    host = f"[{credential.host}]" if ":" in credential.host else credential.host
    return f"{scheme}://{host}{port}"


def normalize_server_url(raw: str, *, allow_insecure_http: bool) -> tuple[str, str, int | None]:
    """(корень, хост, порт); только https, а http для localhost или с разрешения администратора."""
    try:
        parts = urlsplit(raw.strip())
        port = parts.port
    except ValueError:
        raise StudioServerError(StudioServerErrorCode.url_invalid) from None
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"https", "http"} or not host or parts.username or parts.password:
        raise _url_invalid()
    if parts.scheme == "http" and host not in _LOOPBACK and not allow_insecure_http:
        raise _url_invalid()
    shown = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{shown}{f':{port}' if port else ''}", host, port


def _url_invalid() -> StudioServerError:
    return StudioServerError(StudioServerErrorCode.url_invalid)


class StudioServerLogins:
    """Входы на серверы в памяти процесса: одна локальная Студия, один человек."""

    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic
        self._items: dict[str, tuple[float, StudioServerLogin]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def put(self, login: StudioServerLogin) -> None:
        self._evict()
        self._items[login.login_id] = (self._monotonic(), login)

    def get(self, login_id: str) -> StudioServerLogin | None:
        self._evict()
        found = self._items.get(login_id)
        return found[1] if found else None

    def attach(self, login_id: str, task: asyncio.Task[None]) -> None:
        self._tasks[login_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(login_id, None))

    def cancel(self, login_id: str) -> bool:
        task = self._tasks.pop(login_id, None)
        if task is not None:
            task.cancel()
        return self._items.pop(login_id, None) is not None

    def _evict(self) -> None:
        horizon = self._monotonic() - _KEEP_S
        for login_id in [k for k, (at, _) in self._items.items() if at < horizon]:
            self.cancel(login_id)


class StudioServersService:
    def __init__(  # noqa: PLR0913 — порты одного сценария
        self,
        client: IStudioServerClient,
        credentials: IGitCredentialRepository,
        host_settings: IGitHostSettingsRepository,
        logins: StudioServerLogins,
        *,
        allow_insecure_http: bool = False,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._credentials = credentials
        self._hosts = host_settings
        self._logins = logins
        self._allow_insecure_http = allow_insecure_http
        self._sleep = sleep

    async def _target(self, base_url: str, host: str, port: int | None) -> StudioServerTarget:
        stored = await self._hosts.get(host, port)
        if stored is not None and stored.has_trust:
            await self._hosts.materialize()
            return StudioServerTarget(base_url, self._hosts.trust_file(host, port))
        return StudioServerTarget(base_url)

    async def start_login(self, server_url: str, client_name: str) -> StudioServerLogin:
        base, host, port = normalize_server_url(server_url, allow_insecure_http=self._allow_insecure_http)
        target = await self._target(base, host, port)
        await self._client.info(target)
        grant = await self._client.device_code(target, client_name)
        login = StudioServerLogin(
            login_id=f"gsl_{uuid.uuid4().hex[:12]}",
            server_url=base,
            state=LoginState.pending,
            user_code=grant.user_code,
            verification_uri_complete=grant.verification_uri_complete,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=grant.expires_in),
        )
        self._logins.put(login)
        task = asyncio.get_running_loop().create_task(
            self._poll(login, target, host, port, grant.device_code, grant.interval)
        )
        self._logins.attach(login.login_id, task)
        return login

    async def _poll(  # noqa: PLR0913 — состояние одного входа
        self,
        login: StudioServerLogin,
        target: StudioServerTarget,
        host: str,
        port: int | None,
        code: str,
        interval: int,
    ) -> None:
        try:
            await self._poll_until_done(login, target, host, port, code, interval)
        except asyncio.CancelledError:
            raise
        except StudioServerError as exc:
            self._logins.put(replace(login, state=LoginState.error, code=exc.code))
        except Exception:  # noqa: BLE001 — вход не должен ронять процесс, человек увидит ошибку
            logger.warning("studio server login failed", server=login.server_url, exc_info=True)
            self._logins.put(replace(login, state=LoginState.error, code=StudioServerErrorCode.unreachable))

    async def _poll_until_done(  # noqa: PLR0913 — состояние одного входа
        self,
        login: StudioServerLogin,
        target: StudioServerTarget,
        host: str,
        port: int | None,
        code: str,
        interval: int,
    ) -> None:
        wait = max(1, interval)
        while True:
            await self._sleep(wait)
            reply = await self._client.device_token(target, code)
            if reply.access_token is not None:
                credential_id = await self._save(target, host, port, reply.access_token)
                self._logins.put(replace(login, state=LoginState.approved, credential_id=credential_id))
                return
            if reply.error == "slow_down":
                wait += _SLOW_DOWN_S
            elif reply.error == "access_denied":
                self._logins.put(replace(login, state=LoginState.denied))
                return
            elif reply.error != "authorization_pending":
                self._logins.put(replace(login, state=LoginState.expired))
                return

    async def _save(self, target: StudioServerTarget, host: str, port: int | None, token: Secret) -> UUID:
        account = await self._client.whoami(target, token)
        shown = f"{host}:{port}" if port else host
        credential = GitCredential(
            id=uuid.uuid4(),
            kind=GitCredentialKind.pat,
            label=f"HSE Doc Studio · {shown}",
            host=host,
            username=STUDIO_USERNAME,
            status=CredentialStatus.ok,
            created_at=datetime.now(timezone.utc),
            token_family=token_family(token.reveal()),
            port=port,
            expires_at=account.expires_at,
            origin=DEVICE_ORIGIN,
        )
        await self._credentials.add(credential, token)
        return credential.id

    def get_login(self, login_id: str) -> StudioServerLogin:
        login = self._logins.get(login_id)
        if login is None:
            raise NotFoundError(localized_error("Вход не найден", "Sign-in not found"))
        if login.state == LoginState.pending and login.expires_at and login.expires_at <= datetime.now(timezone.utc):
            return replace(login, state=LoginState.expired)
        return login

    def cancel_login(self, login_id: str) -> None:
        self._logins.cancel(login_id)

    async def list_servers(self) -> list[StudioServerItem]:
        devices = [c for c in await self._credentials.list() if c.origin == DEVICE_ORIGIN]
        return list(await asyncio.gather(*(self._server_item(c) for c in devices)))

    async def _server_item(self, credential: GitCredential) -> StudioServerItem:
        base = server_url_of(credential)
        item = StudioServerItem(
            credential_id=credential.id,
            server_url=base,
            host=credential.host,
            account_name=None,
            scopes=(),
            expires_at=credential.expires_at,
            state="ok",
        )
        if credential.expires_at is not None and credential.expires_at <= datetime.now(timezone.utc):
            return replace(item, state="expired")
        try:
            secret = await self._credentials.get_secret(credential.id)
            account = await self._client.whoami(await self._target(base, credential.host, credential.port), secret)
        except StudioServerError as exc:
            return replace(item, state="revoked" if exc.code == StudioServerErrorCode.unauthorized else "unreachable")
        except GitSyncError:
            return replace(item, state="unreachable")
        return replace(item, account_name=account.name, scopes=account.scopes, expires_at=account.expires_at)

    async def list_projects(self, credential_id: UUID, *, q: str | None, limit: int, offset: int) -> StudioProjectPage:
        credential = await self._credentials.get(credential_id)
        if credential is None or credential.origin != DEVICE_ORIGIN:
            raise NotFoundError(localized_error("Сервер не найден", "Server not found"))
        base = server_url_of(credential)
        secret = await self._credentials.get_secret(credential_id)
        try:
            return await self._client.projects(
                await self._target(base, credential.host, credential.port), secret, q=q, limit=limit, offset=offset
            )
        except StudioServerError as exc:
            if exc.code == StudioServerErrorCode.unauthorized:
                with contextlib.suppress(Exception):
                    await self._credentials.mark(credential_id, CredentialStatus.auth_failed)
                raise GitSyncError(GitErrorCode.auth_failed) from None
            raise

    async def forget(self, credential_id: UUID) -> None:
        credential = await self._credentials.get(credential_id)
        if (
            credential is None
            or credential.origin != DEVICE_ORIGIN
            or not await self._credentials.delete(credential_id)
        ):
            raise NotFoundError(localized_error("Сервер не найден", "Server not found"))
