"""Проекты человека на сервере Студии в списке локальной Студии (docs/design/local-from-cloud.md, раздел «Облако»).

Список строится по входу кодом устройства: что сервер отдаёт этому токену, то и показывается, чужого там нет.
Проект, уже открытый на компьютере, отмечается по идентификатору проекта на сервере (клон хранит его же) и не
дублируется. Открытие скачивает недостающий проект в стандартную папку проектов без выбора папки и адреса.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.client import StudioProject
from hse_doc_studio.core.git_sync.entities import GitOperation, OperationStatus
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.git_sync.clone_project import CloneProjectInput, CloneProjectUC, GetCloneDefaultsUC
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServersService, server_url_of
from hse_doc_studio.use_cases.projects.list_projects import ListProjectsUC

# Сколько проектов одного сервера попадает в список: личных проектов у человека немного.
MAX_CLOUD_PROJECTS = 500


@dataclass(frozen=True)
class CloudProjectView:
    id: str
    name: str
    owner_name: str
    role: str
    can_push: bool
    updated_at: datetime | None
    # Проект уже открыт на этом компьютере: тот же идентификатор среди локальных проектов.
    is_local: bool


@dataclass(frozen=True)
class CloudServerView:
    credential_id: UUID
    server_url: str
    host: str
    state: str
    projects: tuple[CloudProjectView, ...]
    # Сколько проектов у человека на сервере; больше `len(projects)`, если список обрезан.
    total: int


def mark_local(projects: tuple[StudioProject, ...], local_ids: frozenset[str]) -> tuple[CloudProjectView, ...]:
    """Проекты сервера с пометкой «открыт на компьютере»: идентификаторы сравниваются без учёта регистра."""
    return tuple(
        CloudProjectView(
            id=project.id,
            name=project.name,
            owner_name=project.owner_name,
            role=project.role,
            can_push=project.can_push,
            updated_at=project.updated_at,
            is_local=project.id.lower() in local_ids,
        )
        for project in projects
    )


async def local_project_ids(list_projects: ListProjectsUC) -> frozenset[str]:
    return frozenset(str(project.id).lower() for project in (await list_projects.execute()).projects)


class ListCloudProjectsUC:
    def __init__(self, servers: StudioServersService, list_projects: ListProjectsUC) -> None:
        self._servers = servers
        self._list_projects = list_projects

    async def execute(self) -> list[CloudServerView]:
        local_ids = await local_project_ids(self._list_projects)
        found = await self._servers.cloud_projects(max_items=MAX_CLOUD_PROJECTS)
        return [
            CloudServerView(
                credential_id=server.credential_id,
                server_url=server.server_url,
                host=server.host,
                state=server.state,
                projects=mark_local(server.projects, local_ids),
                total=server.total,
            )
            for server in found
        ]


@dataclass(frozen=True)
class OpenCloudProjectResult:
    project_id: UUID
    # None: проект уже открыт на компьютере, скачивать нечего.
    operation: GitOperation | None


class CloudOpens:
    """Скачивания облачных проектов, которые идут сейчас: проект и его операция клонирования (живёт весь процесс)."""

    def __init__(self) -> None:
        self._running: dict[UUID, str] = {}

    def start(self, project_id: UUID, operation_id: str) -> None:
        self._running[project_id] = operation_id

    def running(self, project_id: UUID, operations: IGitOperationRegistry) -> GitOperation | None:
        operation_id = self._running.get(project_id)
        operation = operations.get(operation_id) if operation_id is not None else None
        if operation is None or operation.status is not OperationStatus.running:
            self._running.pop(project_id, None)
            return None
        return operation


class OpenCloudProjectUC:
    """Открыть проект сервера на компьютере: уже есть, значит открыть, иначе скачать в стандартную папку."""

    def __init__(
        self,
        servers: StudioServersService,
        list_projects: ListProjectsUC,
        clone: CloneProjectUC,
        defaults: GetCloneDefaultsUC,
        operations: IGitOperationRegistry,
        opens: CloudOpens,
    ) -> None:
        self._servers = servers
        self._list_projects = list_projects
        self._clone = clone
        self._defaults = defaults
        self._operations = operations
        self._opens = opens

    async def execute(self, credential_id: UUID, project_id: UUID) -> OpenCloudProjectResult:
        if str(project_id) in await local_project_ids(self._list_projects):
            return OpenCloudProjectResult(project_id, None)
        # Повторное нажатие, пока проект скачивается, подхватывает ту же операцию, а не качает второй раз.
        running = self._opens.running(project_id, self._operations)
        if running is not None:
            return OpenCloudProjectResult(project_id, running)
        found = await self._servers.find_project(credential_id, project_id)
        folder = await self._defaults.execute(found.project.name)
        operation = await self._clone.execute(
            CloneProjectInput(
                url=f"{found.server_url}/git/{project_id}.git",
                folder=str(folder),
                credential_id=credential_id,
                name=found.project.name,
                # По http сюда доходит только свой компьютер: вход на сервер другого адреса по http не получить.
                insecure_http=found.server_url.startswith("http://"),
            )
        )
        self._opens.start(project_id, operation.id)
        return OpenCloudProjectResult(project_id, operation)


# --- Клонирование по адресу облачного проекта (тул MCP `clone_cloud_project`) ---

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_DEFAULT_PORTS = {"https": 443, "http": 80}
_POLL_S = 0.5


class CloudAddressError(ValueError):
    """Адрес проекта не разобран; текст без самого адреса (в нём мог оказаться токен)."""


class CloudServerNotConnectedError(LookupError):
    """На сервер из адреса локальная Студия не входила: сохранённого доступа нет."""

    def __init__(self, host: str | None) -> None:
        super().__init__(host or "")
        self.host = host


@dataclass(frozen=True)
class CloudProjectAddress:
    project_id: UUID
    # Сервер из адреса; None: искать проект на всех подключённых серверах.
    host: str | None = None
    port: int | None = None


def _server_part(raw: str) -> tuple[str, int | None, str]:
    """(хост, порт, путь) адреса; логин и пароль в адресе отклоняются, а сам адрес в ошибку не попадает."""
    try:
        parts = urlsplit(raw.strip())
        port = parts.port
    except ValueError:
        raise CloudAddressError(
            localized_error("Адрес облачного проекта не разобран", "The cloud project address is not valid")
        ) from None
    if parts.username or parts.password:
        raise CloudAddressError(
            localized_error(
                "Адрес не должен содержать логин или токен: доступ к серверу Студия берёт из сохранённого входа",
                "The address must not contain a login or token: the Studio uses the saved server login",
            )
        )
    host = (parts.hostname or "").lower()
    if parts.scheme not in _DEFAULT_PORTS or not host:
        raise CloudAddressError(
            localized_error(
                "Нужен адрес вида https://<сервер>/projects/<id>/", "An address like https://<server>/projects/<id>/"
            )
        )
    return host, _port(port), parts.path


def _port(port: int | None) -> int | None:
    return None if port in _DEFAULT_PORTS.values() else port


def parse_cloud_project_address(url: str | None, project_id: str | None, server: str | None) -> CloudProjectAddress:
    """Адрес проекта (`https://host/projects/<id>/`, `.../git/<id>.git`) или id с необязательным адресом сервера."""
    if url:
        host, port, path = _server_part(url)
        found = _UUID_RE.findall(path)
        # Идентификатор из адреса проекта; адрес одного сервера дополняется project_id.
        wanted = found[0] if found else project_id
        if not wanted:
            raise CloudAddressError(
                localized_error("В адресе нет идентификатора проекта", "The address has no project identifier")
            )
    elif project_id:
        host, port = (None, None) if not server else _server_part(server)[:2]
        wanted = project_id
    else:
        raise CloudAddressError(localized_error("Укажите url или project_id", "Specify url or project_id"))
    try:
        return CloudProjectAddress(UUID(wanted.strip()), host, port)
    except ValueError:
        raise CloudAddressError(
            localized_error("project_id: ожидается UUID проекта", "project_id: a project UUID is expected")
        ) from None


@dataclass(frozen=True)
class CloudCloneOutcome:
    project_id: UUID
    server_url: str | None
    # already_local, running, succeeded, failed, cancelled
    status: str
    operation: GitOperation | None = None


class CloneCloudProjectUC:
    """Скачать облачный проект в локальную Студию по его адресу, тем же путём, что кнопка «Открыть» в списке.

    Доступ берётся из сохранённого входа на сервер (вход кодом устройства); сам токен из сценария не выходит.
    Скачивание идёт в фоне: сценарий ждёт его до `wait_s` секунд, повторный вызов подхватывает ту же операцию.
    """

    def __init__(
        self,
        servers: StudioServersService,
        opener: OpenCloudProjectUC,
        operations: IGitOperationRegistry,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._servers = servers
        self._opener = opener
        self._operations = operations
        self._sleep = sleep
        self._monotonic = monotonic

    async def execute(self, address: CloudProjectAddress, *, wait_s: float) -> CloudCloneOutcome:
        candidates = [
            c
            for c in await self._servers.device_credentials()
            if address.host is None or (c.host.lower(), _port(c.port)) == (address.host, address.port)
        ]
        if not candidates:
            raise CloudServerNotConnectedError(address.host)
        last_missing: NotFoundError | None = None
        for credential in candidates:
            try:
                opened = await self._opener.execute(credential.id, address.project_id)
            except NotFoundError as exc:
                last_missing = exc
                continue
            server_url = server_url_of(credential)
            if opened.operation is None:
                return CloudCloneOutcome(address.project_id, server_url, "already_local")
            operation = await self._wait(opened.operation, wait_s)
            return CloudCloneOutcome(address.project_id, server_url, operation.status.value, operation)
        assert last_missing is not None  # noqa: S101 — кандидаты были, и каждый ответил «не найден»
        raise last_missing

    async def _wait(self, operation: GitOperation, wait_s: float) -> GitOperation:
        deadline = self._monotonic() + max(0.0, wait_s)
        current = operation
        while current.status is OperationStatus.running and self._monotonic() < deadline:
            await self._sleep(_POLL_S)
            current = self._operations.get(operation.id) or current
        return current
