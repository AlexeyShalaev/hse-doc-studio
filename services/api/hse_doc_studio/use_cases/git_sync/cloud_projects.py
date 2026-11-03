"""Проекты человека на сервере Студии в списке локальной Студии (docs/design/local-from-cloud.md, раздел «Облако»).

Список строится по входу кодом устройства: что сервер отдаёт этому токену, то и показывается, чужого там нет.
Проект, уже открытый на компьютере, отмечается по идентификатору проекта на сервере (клон хранит его же) и не
дублируется. Открытие скачивает недостающий проект в стандартную папку проектов без выбора папки и адреса.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.git_remote.client import StudioProject
from hse_doc_studio.core.git_sync.entities import GitOperation, OperationStatus
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry
from hse_doc_studio.use_cases.git_sync.clone_project import CloneProjectInput, CloneProjectUC, GetCloneDefaultsUC
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServersService
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
