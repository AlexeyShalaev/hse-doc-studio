"""Присутствие локальной Студии на сервере (docs/design/connected-devices.md, раздел 6).

Раз в интервал, который называет сервер (по умолчанию минута), Студия шлёт по входу кодом устройства короткий
сигнал: имя устройства, версию, что она делает, состояние раннера и моделей и синхронизацию облачных проектов.
Без постоянного соединения и без содержимого: ни путей, ни текстов документов, ни ключей. Несколько серверов это
несколько независимых сигналов, по одному на сервер.
"""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import structlog

from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.devices.entities import MAX_MODELS, MAX_PROJECTS
from hse_doc_studio.core.devices.local import IDeviceIdentity, LocalDevice
from hse_doc_studio.core.git_remote.client import JsonObject, StudioServerError, studio_project_id
from hse_doc_studio.core.git_sync.entities import GitCredential, SyncUiState
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, IGitRemoteRegistry, IGitStoreRemotes
from hse_doc_studio.core.remote_runner import IRemoteRunnerSupervisor, RemoteRunnerState
from hse_doc_studio.core.repositories import IAIProviderRepository, IProjectRepository
from hse_doc_studio.use_cases.git_sync.status import GitStatusBuilder
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServersService, server_url_of

logger = structlog.get_logger()

DEFAULT_INTERVAL_S = 60
MIN_INTERVAL_S = 15
MAX_INTERVAL_S = 300
# Без входа на сервер тик почти ничего не стоит (читается список доступов): вход подхватывается быстро.
IDLE_INTERVAL_S = 30
_PROBE_TIMEOUT_S = 3.0
_PROBE_TTL_S = 50.0
_OVERVIEW_TTL_S = 10.0
_SYNC_CODES = {
    SyncUiState.up_to_date: "synced",
    SyncUiState.unfetched: "unfetched",
    SyncUiState.ahead: "ahead",
    SyncUiState.behind: "behind",
    SyncUiState.diverged: "diverged",
    SyncUiState.syncing: "syncing",
    SyncUiState.conflicts: "conflicts",
    SyncUiState.auth_failed: "auth_failed",
    SyncUiState.offline: "offline",
    SyncUiState.error: "error",
    SyncUiState.blocked: "blocked",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def os_name(configured: str | None = None, *, in_container: bool = False) -> str:
    """Семейство ОС для списка устройств. Внутри контейнера платформа это Linux виртуальной машины, а не машины
    человека: без подсказки установщика (`HSE_STUDIO__DEVICE_OS`) она остаётся неизвестной."""
    if configured in {"macos", "windows", "linux"}:
        return configured
    if in_container:
        return "other"
    return {"darwin": "macos", "windows": "windows", "linux": "linux"}.get(platform.system().lower(), "other")


@dataclass(frozen=True)
class LastPresence:
    at: datetime
    ok: bool
    code: str | None = None
    interval_s: int = DEFAULT_INTERVAL_S
    online_window_s: int = 180


@dataclass
class PresenceBoard:
    """Что Студия помнит о сигналах: когда ушёл последний, чем кончился и недавний ответ сервера «как вы выглядите»."""

    sent: dict[UUID, LastPresence] = field(default_factory=dict)
    overview: dict[tuple[UUID, UUID | None], tuple[float, JsonObject]] = field(default_factory=dict)
    probes: dict[str, tuple[float, bool, tuple[str, ...]]] = field(default_factory=dict)


@dataclass(frozen=True)
class PresenceTick:
    sent: int = 0
    failed: int = 0
    # Через сколько секунд идти снова: сервер называет интервал сам, а без серверов Студия спит подолгу.
    next_in_s: int = DEFAULT_INTERVAL_S
    servers: int = 0


@dataclass(frozen=True)
class LocalEndpointView:
    name: str
    flavor: str
    announced: bool
    reachable: bool | None
    models: tuple[str, ...]


@dataclass(frozen=True)
class LocalRunnerView:
    state: str
    paired: bool
    name: str | None
    running_jobs: int
    enabled: bool


@dataclass(frozen=True)
class LinkServer:
    credential_id: UUID
    server_url: str
    host: str
    state: str
    account_name: str | None
    last: LastPresence | None
    cloud: JsonObject | None
    cloud_error: str | None


@dataclass(frozen=True)
class StudioLink:
    device: LocalDevice
    runner: LocalRunnerView
    endpoints: tuple[LocalEndpointView, ...]
    servers: tuple[LinkServer, ...]
    # Состояние облачного проекта на этой Студии (когда спросили про проект).
    project: JsonObject | None = None


class LocalPresenceService:
    def __init__(  # noqa: PLR0913 — порты одного сценария
        self,
        *,
        identity: IDeviceIdentity,
        servers: StudioServersService,
        registry: IGitRemoteRegistry,
        project_repo: IProjectRepository,
        store_remotes: IGitStoreRemotes,
        status: GitStatusBuilder,
        operations: IGitOperationRegistry,
        supervisor: IRemoteRunnerSupervisor,
        providers: IAIProviderRepository,
        model_lister: IAIModelLister,
        busy_building: Callable[[], bool],
        board: PresenceBoard,
        version: str,
        os_hint: str | None = None,
        in_container: bool = False,
        clock: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._identity = identity
        self._servers = servers
        self._registry = registry
        self._projects = project_repo
        self._remotes = store_remotes
        self._status = status
        self._operations = operations
        self._supervisor = supervisor
        self._providers = providers
        self._lister = model_lister
        self._busy_building = busy_building
        self._board = board
        self._version = version
        self._os = os_name(os_hint, in_container=in_container)
        self._clock = clock
        import time  # noqa: PLC0415

        self._monotonic = monotonic or time.monotonic

    async def tick(self) -> PresenceTick:
        """Один проход: сигнал на каждый сервер Студии, куда есть вход. Сбой одного сервера не мешает остальным."""
        credentials = await self._servers.device_credentials()
        if not credentials:
            return PresenceTick(next_in_s=IDLE_INTERVAL_S)
        device = await self._identity.get()
        endpoints = await self._endpoints()
        outcomes = await asyncio.gather(*(self._send(c, device, endpoints) for c in credentials))
        failed = outcomes.count(None)
        replies = [o for o in outcomes if o is not None]
        interval = min((r for r in replies), default=DEFAULT_INTERVAL_S)
        # Сбой связи не должен давать шквал повторов: после неудачи ждём не меньше обычного интервала.
        wait = max(interval, DEFAULT_INTERVAL_S) if failed else interval
        return PresenceTick(
            sent=len(replies),
            failed=failed,
            next_in_s=min(max(wait, MIN_INTERVAL_S), MAX_INTERVAL_S),
            servers=len(credentials),
        )

    async def _send(
        self, credential: GitCredential, device: LocalDevice, endpoints: tuple[LocalEndpointView, ...]
    ) -> int | None:
        """Интервал из ответа сервера или None, если сигнал не дошёл."""
        now = self._clock()
        try:
            report = await self.build_report(credential, device, endpoints)
            reply = await self._servers.send_presence(credential.id, report)
        except (StudioServerError, GitSyncError) as exc:
            code = exc.code if isinstance(exc, StudioServerError) else exc.code.value
            self._board.sent[credential.id] = LastPresence(now, False, code)
            return None
        except Exception:  # noqa: BLE001 — присутствие вторично и не должно ронять фоновый цикл
            logger.warning("presence send failed", server=credential.host, exc_info=True)
            self._board.sent[credential.id] = LastPresence(now, False, "unexpected")
            return None
        self._board.sent[credential.id] = LastPresence(now, True, None, reply.interval_s, reply.online_window_s)
        return reply.interval_s

    # --- сигнал -----------------------------------------------------------------------------------------------

    async def build_report(
        self, credential: GitCredential, device: LocalDevice, endpoints: tuple[LocalEndpointView, ...]
    ) -> JsonObject:
        status = self._supervisor.status()
        projects = await self._project_reports(credential)
        busy = self._busy_building()
        syncing = any(p["sync"] == "syncing" for p in projects)
        runner: JsonObject | None = None
        if status.paired and status.runner_id:
            runner = {
                "runner_id": status.runner_id,
                "state": status.state.value,
                "running_jobs": status.running_jobs,
            }
        return {
            "device_id": device.device_id,
            "name": device.name,
            "version": self._version,
            "os": self._os,
            "activity": "building" if busy else "syncing" if syncing else "idle",
            "runner": runner,
            "endpoints": [
                {"name": e.name, "flavor": e.flavor, "reachable": e.reachable, "models": list(e.models)[:MAX_MODELS]}
                for e in endpoints
                if e.announced
            ],
            "projects": projects[:MAX_PROJECTS],
        }

    async def _project_reports(self, credential: GitCredential) -> list[JsonObject]:
        reports: list[JsonObject] = []
        for folder in await self._registry.list():
            try:
                report = await self._project_report(folder, credential)
            except Exception:  # noqa: BLE001 — один сломанный проект не должен скрыть остальные
                logger.warning("presence project report failed", exc_info=True)
                continue
            if report is not None:
                reports.append(report)
        return reports

    async def project_report(self, project_id: UUID, credential: GitCredential) -> JsonObject | None:
        for folder in await self._registry.list():
            report = await self._project_report(folder, credential)
            if report is not None and report["project_id"] == str(project_id):
                return report
        return None

    async def _project_report(self, folder: object, credential: GitCredential) -> JsonObject | None:
        project = await asyncio.to_thread(self._projects.get, folder)  # type: ignore[arg-type]
        if project is None:
            return None
        config = await asyncio.to_thread(self._remotes.read, project)
        if config is None:
            return None
        project_id = studio_project_id(config.url)
        if project_id is None or not _same_server(config.url, credential):
            return None
        view = await self._status.view(project)
        sync = "syncing" if self._operations.current_for(project.id) is not None else _SYNC_CODES.get(view.ui_state)
        if sync is None:
            return None
        last = view.pdf_upload.last
        return {
            "project_id": str(project_id),
            "sync": sync,
            "ahead": view.ahead,
            "behind": view.behind,
            "last_sync_at": view.last_sync_at.isoformat() if view.last_sync_at else None,
            "auto_sync": view.auto_sync.enabled,
            "pdf": None
            if last is None
            else {"doc_id": last.doc_id, "at": last.at.isoformat(), "ok": last.ok, "code": last.code},
        }

    # --- модели через Студию ---------------------------------------------------------------------------------

    async def _endpoints(self) -> tuple[LocalEndpointView, ...]:
        views: list[LocalEndpointView] = []
        for info in self._supervisor.status().ai_endpoints:
            reachable, models = await self._probe(info.provider_id)
            views.append(
                LocalEndpointView(
                    name=info.name, flavor=info.flavor, announced=info.announced, reachable=reachable, models=models
                )
            )
        return tuple(views)

    async def _probe(self, provider_id: str) -> tuple[bool | None, tuple[str, ...]]:
        """Отвечает ли модель на этой машине и какие есть; короткий опрос с запоминанием, чтобы не нагружать Ollama."""
        now = self._monotonic()
        cached = self._board.probes.get(provider_id)
        if cached is not None and now - cached[0] < _PROBE_TTL_S:
            return cached[1], cached[2]
        try:
            provider = await self._providers.get(UUID(provider_id))
        except ValueError:
            return None, ()
        if provider is None:
            return None, ()
        try:
            # Ollama и другие локальные модели ключа не требуют, а SDK без ключа отказывает до запроса.
            keyed = replace(provider, api_key=provider.api_key or "not-needed")
            models = await asyncio.wait_for(self._lister.list_models(keyed), timeout=_PROBE_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 — любая причина значит «не отвечает»
            logger.debug("presence model probe failed", error=type(exc).__name__, detail=str(exc)[:200])
            self._board.probes[provider_id] = (now, False, ())
            return False, ()
        found = tuple(models[:MAX_MODELS])
        self._board.probes[provider_id] = (now, True, found)
        return True, found

    # --- вид для окна Студии ------------------------------------------------------------------------------------

    async def link(self, project_id: UUID | None) -> StudioLink:
        device = await self._identity.get()
        endpoints = await self._endpoints()
        status = self._supervisor.status()
        runner = LocalRunnerView(
            state=status.state.value,
            paired=status.paired,
            name=status.runner_name,
            running_jobs=status.running_jobs,
            enabled=status.settings.enabled and status.state is not RemoteRunnerState.off,
        )
        listed = {s.credential_id: s for s in await self._servers.list_servers()}
        credentials = await self._servers.device_credentials()
        chosen = {(c.host, c.port): c for c in credentials}
        items: list[LinkServer] = []
        project_state: JsonObject | None = None
        for credential in chosen.values():
            server = listed.get(credential.id)
            state = server.state if server is not None else "ok"
            cloud, error = (None, None)
            if state == "ok":
                cloud, error = await self._cloud_view(credential, device, project_id)
                if project_id is not None and project_state is None:
                    project_state = await self.project_report(project_id, credential)
            items.append(
                LinkServer(
                    credential_id=credential.id,
                    server_url=server_url_of(credential),
                    host=credential.host,
                    state=state,
                    account_name=server.account_name if server is not None else None,
                    last=self._board.sent.get(credential.id),
                    cloud=cloud,
                    cloud_error=error,
                )
            )
        # Серверы, куда вход есть, но он отказал или истёк: человек должен видеть, что связи нет.
        for item_id, server in listed.items():
            if all(item.credential_id != item_id for item in items) and (server.host, None) not in {
                (i.host, None) for i in items
            }:
                items.append(
                    LinkServer(
                        credential_id=item_id,
                        server_url=server.server_url,
                        host=server.host,
                        state=server.state,
                        account_name=server.account_name,
                        last=self._board.sent.get(item_id),
                        cloud=None,
                        cloud_error=None,
                    )
                )
        return StudioLink(device, runner, endpoints, tuple(items), project_state)

    async def _cloud_view(
        self, credential: GitCredential, device: LocalDevice, project_id: UUID | None
    ) -> tuple[JsonObject | None, str | None]:
        key = (credential.id, project_id)
        now = self._monotonic()
        cached = self._board.overview.get(key)
        if cached is not None and now - cached[0] < _OVERVIEW_TTL_S:
            return cached[1], None
        try:
            overview = await self._servers.presence_overview(credential.id, device.device_id, project_id)
        except StudioServerError as exc:
            return None, exc.code
        except GitSyncError as exc:
            return None, exc.code.value
        self._board.overview[key] = (now, overview)
        return overview, None


def _normal_port(port: int | None, scheme: str) -> int | None:
    return None if port is None or (scheme, port) in {("https", 443), ("http", 80)} else port


def _same_server(url: str, credential: GitCredential) -> bool:
    """Адрес клонирования проекта принадлежит этому серверу (хост и порт входа)."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    scheme = "http" if credential.host in {"localhost", "127.0.0.1", "::1"} else "https"
    if (parts.hostname or "").lower() != credential.host.lower():
        return False
    return _normal_port(port, parts.scheme) == _normal_port(credential.port, scheme)
