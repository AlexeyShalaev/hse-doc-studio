"""API хостинга git для Студии шаблонов (template-studio.md, D8 и 4.4; срез T6): PR GitHub, форк, статус проверок.

MR GitLab открывается push options (хватает `write_repository`), поэтому здесь от GitLab нужен только статус
конвейера (`read_api`). Токен берётся через тот же `ICredentialAccess`, что у git рабочего пространства, уходит
только в заголовке на корень API этого хоста и не попадает ни в ответы, ни в ошибки. Перенаправления выключены,
тело ответа ограничено, сертификат проверяется полностью (свой CA сервера, как у git), на общем сервере адрес
проходит политику egress.
"""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx
import structlog

from hse_doc_studio.core.egress import EgressBlockedError, IEgressPolicy
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import ICredentialAccess
from hse_doc_studio.core.git_sync.providers import GitProvider
from hse_doc_studio.core.git_sync.untrusted_json import loads_untrusted
from hse_doc_studio.core.git_sync.url import LOOPBACK_HOSTS
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.git_flow import (
    CheckState,
    CiCheck,
    CiReport,
    CiState,
    ForkRef,
    HostingAccount,
    HostingRepo,
    PullRequestRef,
    PullRequestState,
    RepoPermissions,
    checks_page_url,
    summarize_checks,
)
from hse_doc_studio.infra.egress.http import egress_client
from hse_doc_studio.infra.git_sync.egress_guard import egress_error
from hse_doc_studio.infra.git_sync.tls_certificates import verifying_ssl_context

logger = structlog.get_logger()

_USER_AGENT = "HSE-Doc-Studio"
_MAX_BODY_BYTES = 2_000_000
_TOTAL_TIMEOUT_FACTOR = 2.0
_PER_PAGE = 100
_OK = 200
_CREATED = 201
_ACCEPTED = 202
_UNPROCESSABLE = 422
_DENIED = frozenset({401, 403, 404})
# GitLab: Developer (30) и выше может отправлять в незащищённые ветки.
_GITLAB_DEVELOPER = 30

_GITHUB_RUN_STATE = {"queued": CheckState.queued, "in_progress": CheckState.running, "waiting": CheckState.queued}
_GITHUB_CONCLUSION = {
    "success": CheckState.success,
    "neutral": CheckState.neutral,
    "skipped": CheckState.skipped,
    "cancelled": CheckState.cancelled,
    "failure": CheckState.failure,
    "timed_out": CheckState.failure,
    "action_required": CheckState.failure,
    "stale": CheckState.neutral,
}
_GITHUB_STATUS = {
    "pending": CheckState.running,
    "success": CheckState.success,
    "failure": CheckState.failure,
    "error": CheckState.failure,
}
_GITLAB_STATUS = {
    "created": CheckState.queued,
    "waiting_for_resource": CheckState.queued,
    "preparing": CheckState.queued,
    "pending": CheckState.queued,
    "scheduled": CheckState.queued,
    "running": CheckState.running,
    "success": CheckState.success,
    "failed": CheckState.failure,
    "canceled": CheckState.cancelled,
    "canceling": CheckState.cancelled,
    "skipped": CheckState.skipped,
    "manual": CheckState.neutral,
}


@dataclass(frozen=True)
class _Reply:
    status: int
    data: Any
    headers: Mapping[str, str] | None = None

    @property
    def ok(self) -> bool:
        return self.status in {_OK, _CREATED, _ACCEPTED}

    def obj(self) -> dict[str, Any]:
        return self.data if isinstance(self.data, dict) else {}

    def items(self) -> list[dict[str, Any]]:
        return [item for item in self.data if isinstance(item, dict)] if isinstance(self.data, list) else []


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _short(value: object, limit: int = 200) -> str | None:
    text = _text(value)
    return None if text is None else " ".join(text.split())[:limit]


class HttpPackHosting:
    def __init__(
        self,
        access: ICredentialAccess,
        *,
        timeout_s: float,
        egress: IEgressPolicy | None = None,
        allow_insecure_http: bool = False,
        allow_loopback_http: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._access = access
        self._timeout_s = timeout_s
        self._egress = egress
        self._allow_insecure_http = allow_insecure_http
        self._allow_loopback_http = allow_loopback_http
        self._transport = transport

    # ── порт ──

    async def permissions(self, repo: HostingRepo, target: RemoteTarget) -> RepoPermissions:
        if repo.api_base is None:
            return RepoPermissions(can_push=None)
        if repo.provider is GitProvider.github:
            reply = await self._call(repo, target, "GET", f"/repos/{repo.path}")
            perms = reply.obj().get("permissions")
            if reply.status == _OK and isinstance(perms, dict) and isinstance(perms.get("push"), bool):
                return RepoPermissions(can_push=bool(perms["push"]))
            return RepoPermissions(can_push=None)
        if repo.provider is GitProvider.gitlab:
            reply = await self._call(repo, target, "GET", f"/projects/{_gitlab_id(repo.path)}")
            perms = reply.obj().get("permissions")
            if reply.status != _OK or not isinstance(perms, dict):
                return RepoPermissions(can_push=None)
            levels = [
                level
                for key in ("project_access", "group_access")
                if isinstance(entry := perms.get(key), dict) and isinstance(level := entry.get("access_level"), int)
            ]
            return RepoPermissions(can_push=max(levels, default=0) >= _GITLAB_DEVELOPER)
        return RepoPermissions(can_push=None)

    async def fork(self, repo: HostingRepo, target: RemoteTarget, *, create: bool) -> ForkRef | None:
        if repo.provider is not GitProvider.github or repo.api_base is None:
            return None
        user = await self._call(repo, target, "GET", "/user")
        login = _text(user.obj().get("login"))
        if user.status == _OK and login:
            mine = await self._call(repo, target, "GET", f"/repos/{login}/{repo.name}")
            found = _fork_of(mine, repo)
            if found is not None:
                return found
        if not create:
            return None
        made = await self._call(repo, target, "POST", f"/repos/{repo.path}/forks", json={})
        body = made.obj()
        full_name, clone_url = _text(body.get("full_name")), _text(body.get("clone_url"))
        if made.ok and full_name and clone_url:
            return ForkRef(path=full_name, clone_url=clone_url)
        return None

    async def open_pull_request(
        self, repo: HostingRepo, target: RemoteTarget, *, head: str, base: str, title: str, body: str
    ) -> PullRequestRef:
        if repo.provider is not GitProvider.github or repo.api_base is None:
            raise PackStudioError(PackStudioErrorCode.pr_permission_missing)
        payload = {"title": title, "head": head, "base": base, "body": body, "maintainer_can_modify": True}
        reply = await self._call(repo, target, "POST", f"/repos/{repo.path}/pulls", json=payload)
        found = _pull(reply.obj(), created=True)
        if reply.status == _CREATED and found is not None:
            return found
        if reply.status == _UNPROCESSABLE:
            query = urlencode({"head": head, "base": base, "state": "open"})
            existing = await self._call(repo, target, "GET", f"/repos/{repo.path}/pulls?{query}")
            for item in existing.items():
                if (pull := _pull(item, created=False)) is not None:
                    return pull
        if reply.status in _DENIED or reply.status == _UNPROCESSABLE:
            raise PackStudioError(PackStudioErrorCode.pr_permission_missing, status=reply.status)
        raise git_error(GitErrorCode.git_error, tail=f"HTTP {reply.status}")

    async def ci_status(self, repo: HostingRepo, target: RemoteTarget, *, sha: str, branch: str | None) -> CiReport:
        page = checks_page_url(repo, branch=branch, sha=sha)
        unavailable = CiReport(
            state=CiState.unknown,
            sha=sha,
            available=False,
            reason=PackStudioErrorCode.ci_status_unavailable.value,
            web_url=page,
        )
        if repo.api_base is None:
            return unavailable
        if repo.provider is GitProvider.github:
            return await self._github_checks(repo, target, sha, page) or unavailable
        if repo.provider is GitProvider.gitlab:
            return await self._gitlab_pipeline(repo, target, sha, page) or unavailable
        return unavailable

    async def pull_request_state(self, repo: HostingRepo, target: RemoteTarget, number: int) -> PullRequestState | None:
        if repo.provider is not GitProvider.github or repo.api_base is None:
            return None
        reply = await self._call(repo, target, "GET", f"/repos/{repo.path}/pulls/{number}")
        body = reply.obj()
        if reply.status != _OK:
            return None
        if body.get("merged") is True or _text(body.get("merged_at")):
            return PullRequestState.merged
        state = body.get("state")
        if state == "open":
            return PullRequestState.open
        return PullRequestState.closed if state == "closed" else None

    async def account(self, repo: HostingRepo, target: RemoteTarget) -> HostingAccount | None:
        if repo.provider is not GitProvider.github or repo.api_base is None:
            return None
        reply = await self._call(repo, target, "GET", "/user")
        login = _text(reply.obj().get("login"))
        if reply.status != _OK or login is None:
            return None
        raw = (reply.headers or {}).get("x-oauth-scopes")
        scopes = None if raw is None else tuple(part.strip() for part in raw.split(",") if part.strip())
        return HostingAccount(login=login, scopes=scopes)

    # ── GitHub и GitLab ──

    async def _github_checks(
        self, repo: HostingRepo, target: RemoteTarget, sha: str, page: str | None
    ) -> CiReport | None:
        """`check-runs` (только классический токен или GitHub App) и статусы коммита (`Commit statuses: Read`)."""
        runs = await self._call(
            repo, target, "GET", f"/repos/{repo.path}/commits/{sha}/check-runs?per_page={_PER_PAGE}"
        )
        statuses = await self._call(
            repo, target, "GET", f"/repos/{repo.path}/commits/{sha}/status?per_page={_PER_PAGE}"
        )
        if _OK not in (runs.status, statuses.status):
            return None
        checks: list[CiCheck] = await self._github_awaiting_approval(repo, target, sha)
        raw_runs = runs.obj().get("check_runs") if runs.status == _OK else None
        for run in raw_runs if isinstance(raw_runs, list) else []:
            if not isinstance(run, dict):
                continue
            if run.get("status") == "completed":
                state = _GITHUB_CONCLUSION.get(str(run.get("conclusion")), CheckState.neutral)
            else:
                state = _GITHUB_RUN_STATE.get(str(run.get("status")), CheckState.queued)
            output = run.get("output") if isinstance(run.get("output"), dict) else {}
            checks.append(
                CiCheck(
                    name=_short(run.get("name"), 120) or "check",
                    state=state,
                    url=_text(run.get("html_url")),
                    summary=_short(output.get("title")) if isinstance(output, dict) else None,
                )
            )
        raw_statuses = statuses.obj().get("statuses") if statuses.status == _OK else None
        for status in raw_statuses if isinstance(raw_statuses, list) else []:
            if not isinstance(status, dict):
                continue
            checks.append(
                CiCheck(
                    name=_short(status.get("context"), 120) or "status",
                    state=_GITHUB_STATUS.get(str(status.get("state")), CheckState.queued),
                    url=_text(status.get("target_url")),
                    summary=_short(status.get("description")),
                )
            )
        return CiReport(state=summarize_checks(checks), sha=sha, checks=tuple(checks), web_url=page)

    async def _github_awaiting_approval(self, repo: HostingRepo, target: RemoteTarget, sha: str) -> list[CiCheck]:
        """Запуски Actions по коммиту, которые ждут одобрения сопровождающего (PR из форка нового участника, T22).

        Такие запуски не создают проверок (`check-runs` пуст), поэтому без этого запроса статус выглядел бы вечным
        «нет проверок». GitHub помечает их `conclusion: action_required` (или `status: action_required`).
        """
        try:
            reply = await self._call(
                repo, target, "GET", f"/repos/{repo.path}/actions/runs?head_sha={sha}&per_page={_PER_PAGE}"
            )
        except GitSyncError:
            return []
        raw = reply.obj().get("workflow_runs") if reply.status == _OK else None
        waiting: list[CiCheck] = []
        for run in raw if isinstance(raw, list) else []:
            if not isinstance(run, dict):
                continue
            if "action_required" not in {run.get("status"), run.get("conclusion")}:
                continue
            waiting.append(
                CiCheck(
                    name=_short(run.get("name"), 120) or "workflow",
                    state=CheckState.awaiting_approval,
                    url=_text(run.get("html_url")),
                )
            )
        return waiting

    async def _gitlab_pipeline(
        self, repo: HostingRepo, target: RemoteTarget, sha: str, page: str | None
    ) -> CiReport | None:
        """Последний конвейер по коммиту и его задачи; без `read_api` GitLab отвечает 401 или 403."""
        project = _gitlab_id(repo.path)
        pipelines = await self._call(repo, target, "GET", f"/projects/{project}/pipelines?sha={sha}&per_page=20")
        if pipelines.status != _OK:
            return None
        found = pipelines.items()
        if not found:
            return CiReport(state=CiState.none, sha=sha, web_url=page)
        latest = max(found, key=_pipeline_id)
        web = _text(latest.get("web_url")) or page
        jobs = await self._call(
            repo, target, "GET", f"/projects/{project}/pipelines/{latest.get('id')}/jobs?per_page={_PER_PAGE}"
        )
        checks = [
            CiCheck(
                name=_short(job.get("name"), 120) or "job",
                state=_GITLAB_STATUS.get(str(job.get("status")), CheckState.queued),
                url=_text(job.get("web_url")),
                summary=_short(job.get("stage")),
            )
            for job in (jobs.items() if jobs.status == _OK else [])
        ]
        if not checks:
            checks = [
                CiCheck(
                    name=f"pipeline #{latest.get('id')}",
                    state=_GITLAB_STATUS.get(str(latest.get("status")), CheckState.queued),
                    url=web,
                )
            ]
        return CiReport(state=summarize_checks(checks), sha=sha, checks=tuple(checks), web_url=web)

    # ── HTTP ──

    async def _call(
        self, repo: HostingRepo, target: RemoteTarget, method: str, path: str, json: Mapping[str, Any] | None = None
    ) -> _Reply:
        api = repo.api_base or ""
        self._check_scheme(api, target)
        headers = _headers(repo.provider, await self._token(target))
        try:
            async with (
                self._client(repo) as client,
                asyncio.timeout(self._timeout_s * _TOTAL_TIMEOUT_FACTOR),
                client.stream(method, api + path, headers=headers, json=json) as response,
            ):
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > _MAX_BODY_BYTES:
                        return _Reply(response.status_code, None)
                return _Reply(response.status_code, _parse(bytes(body)), _kept_headers(response.headers))
        except EgressBlockedError:
            raise egress_error() from None
        except (httpx.TimeoutException, TimeoutError):
            raise git_error(GitErrorCode.timeout) from None
        except httpx.ConnectError as exc:
            raise _connect_error(exc) from None
        except (httpx.HTTPError, OSError):
            raise git_error(GitErrorCode.offline) from None

    def _client(self, repo: HostingRepo) -> httpx.AsyncClient:
        options: dict[str, Any] = {"timeout": self._timeout_s, "follow_redirects": False}
        if self._transport is not None:
            return httpx.AsyncClient(transport=self._transport, **options)
        verify = verifying_ssl_context(repo.ca_file)
        if self._egress is None:
            return httpx.AsyncClient(verify=verify, **options)
        return egress_client(self._egress, verify=verify, **options)

    def _check_scheme(self, api: str, target: RemoteTarget) -> None:
        if not api.lower().startswith("http://"):
            return
        host = httpx.URL(api).host
        if self._allow_loopback_http and host in LOOPBACK_HOSTS:
            return
        if self._allow_insecure_http and target.insecure_http:
            return
        raise git_error(GitErrorCode.url_scheme_forbidden)

    async def _token(self, target: RemoteTarget) -> str | None:
        if target.credential_id is None:
            return None
        try:
            secret = await self._access.get_secret(target.credential_id, project_id=None, remote=target.url)
        except NotFoundError:
            raise git_error(GitErrorCode.credentials_missing) from None
        return secret.reveal()


_KEPT_HEADERS = ("x-oauth-scopes",)


def _kept_headers(headers: httpx.Headers) -> dict[str, str]:
    """Только заголовки, которые нужны сценариям (области классического токена GitHub)."""
    return {name: headers[name] for name in _KEPT_HEADERS if name in headers}


def _headers(provider: GitProvider, token: str | None) -> dict[str, str]:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if token is not None:
        headers.update(_auth_header(provider, token))
    if provider is GitProvider.github:
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers


def _connect_error(exc: httpx.ConnectError) -> Exception:
    cause: BaseException | None = exc
    while cause is not None and not isinstance(cause, ssl.SSLError):
        cause = cause.__cause__ or cause.__context__
    return git_error(GitErrorCode.tls_error if cause is not None else GitErrorCode.offline)


def _auth_header(provider: GitProvider, token: str) -> dict[str, str]:
    if provider is GitProvider.gitlab:
        return {"PRIVATE-TOKEN": token}
    if provider is GitProvider.gitea:
        return {"Authorization": f"token {token}"}
    return {"Authorization": f"Bearer {token}"}


def _parse(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return loads_untrusted(raw)
    except ValueError:
        return None


def _pipeline_id(item: Mapping[str, Any]) -> int:
    value = item.get("id")
    return value if isinstance(value, int) else 0


def _gitlab_id(path: str) -> str:
    return quote(path, safe="")


def _pull(body: Mapping[str, Any], *, created: bool) -> PullRequestRef | None:
    number, url = body.get("number"), _text(body.get("html_url"))
    if isinstance(number, int) and url:
        return PullRequestRef(number=number, url=url, created=created)
    return None


def _fork_of(reply: _Reply, repo: HostingRepo) -> ForkRef | None:
    body = reply.obj()
    if reply.status != _OK or body.get("fork") is not True:
        return None
    parent = body.get("parent") if isinstance(body.get("parent"), dict) else {}
    source = body.get("source") if isinstance(body.get("source"), dict) else {}
    wanted = repo.path.lower()
    names = {str(item.get("full_name", "")).lower() for item in (parent, source) if isinstance(item, dict)}
    full_name, clone_url = _text(body.get("full_name")), _text(body.get("clone_url"))
    if wanted not in names or not full_name or not clone_url:
        return None
    return ForkRef(path=full_name, clone_url=clone_url)
