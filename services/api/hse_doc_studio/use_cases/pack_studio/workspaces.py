"""Рабочие пространства Студии шаблонов (docs/design/template-studio.md, 4.1, 4.5, срез T5).

Пространство над git создаётся сразу (`cloning`), клон идёт в фоне: частичный, без блобов, разреженное дерево только
с папкой паков. Клиент опрашивает `GET /workspaces/{id}` до `ready` или `failed`. «Обновить» делает выборку базовой
ветки (рабочее дерево не трогается) и пересчитывает выпущенные версии; у неудачного клона начинает его заново.

Выпущенные версии (D10) это реестры `releases.yaml` базовой ветки после выборки: у пространства над git они
кешируются в `base-releases.json` рядом с хранилищем. Папка (только локально) берёт реестры с диска.

Владелец: на сервере пространство видит только тот, кто его создал (`owner_id`); чужое неотличимо от несуществующего.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitTransport
from hse_doc_studio.core.git_sync.url import RemoteUrl, parse_remote_url
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.pack_studio.entities import (
    PackWorkspace,
    ReleasedVersions,
    WorkspaceError,
    WorkspaceKind,
    WorkspaceState,
)
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import validate_packs_path
from hse_doc_studio.core.pack_studio.protection import Protection
from hse_doc_studio.core.pack_studio.protocols import (
    IPackWorkspaceFiles,
    IPackWorkspaceGit,
    IPackWorkspaceRepository,
    WorkspaceDirs,
    WorkspaceLimits,
)
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.infra.git_sync.auth_env import check_credential_matches
from hse_doc_studio.use_cases.git_sync.probe_remote import raise_probe_error, require_http_consent, valid_branch

logger = structlog.get_logger()

AUDIT_CREATE = "pack_studio.workspace_create"
AUDIT_DELETE = "pack_studio.workspace_delete"
LABEL_MAX = 120
_RELEASES_CACHE = "base-releases.json"


@dataclass(frozen=True)
class CreateWorkspaceInput:
    kind: WorkspaceKind
    label: str | None = None
    # git
    url: str | None = None
    credential_id: UUID | None = None
    insecure_http: bool = False
    base_branch: str | None = None
    # folder (только локально): путь хоста или контейнера
    folder: str | None = None
    # Папка паков внутри репозитория или папки; None: `packs` у git, у папки `packs`, если она есть, иначе сама папка.
    packs_path: str | None = None


@dataclass(frozen=True)
class WorkspaceView:
    workspace: PackWorkspace
    # Идёт фоновая операция (клон или выборка).
    busy: bool
    # Путь папки для показа человеку (путь хоста, если Студия в Docker).
    folder_display: str | None = None


class WorkspaceTasks:
    """Фоновые операции рабочих пространств в памяти процесса: одна на пространство, ссылки держатся до конца."""

    def __init__(self) -> None:
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    def is_busy(self, workspace_id: UUID) -> bool:
        task = self._tasks.get(workspace_id)
        return task is not None and not task.done()

    def spawn(self, workspace_id: UUID, work: Callable[[], Coroutine[Any, Any, None]]) -> None:
        if self.is_busy(workspace_id):
            raise PackStudioError(PackStudioErrorCode.workspace_busy)
        task = asyncio.create_task(work())
        self._tasks[workspace_id] = task
        task.add_done_callback(lambda done: self._forget(workspace_id, done))

    async def cancel(self, workspace_id: UUID) -> None:
        task = self._tasks.get(workspace_id)
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def _forget(self, workspace_id: UUID, task: asyncio.Task[None]) -> None:
        if self._tasks.get(workspace_id) is task:
            del self._tasks[workspace_id]


def _now() -> datetime:
    return datetime.now(UTC)


def owner_of(actor: Actor) -> str | None:
    return None if actor.is_local else actor.id


class PackWorkspaceService:
    def __init__(  # noqa: PLR0913 — порты и пределы развёртывания
        self,
        repo: IPackWorkspaceRepository,
        files: IPackWorkspaceFiles,
        git: IPackWorkspaceGit,
        transport: IGitTransport,
        credentials: IGitCredentialRepository,
        policy: GitSyncPolicy,
        paths: PathMapping,
        tasks: WorkspaceTasks,
        *,
        workspaces_dir: Path,
        limits: WorkspaceLimits,
        max_workspaces: int,
        default_packs_path: str,
        local_mode: bool,
        audit: IAuditLog | None = None,
        dirs_factory: Callable[[Path], WorkspaceDirs],
    ) -> None:
        self._repo = repo
        self._files = files
        self._git = git
        self._transport = transport
        self._credentials = credentials
        self._policy = policy
        self._paths = paths
        self._tasks = tasks
        self._workspaces_dir = workspaces_dir
        self._limits = limits
        self._max = max_workspaces
        self._default_packs_path = default_packs_path
        self._local = local_mode
        self._audit = audit
        self._dirs_factory = dirs_factory

    @property
    def limits(self) -> WorkspaceLimits:
        return self._limits

    # ── чтение ───────────────────────────────────────────────────────────────

    async def list(self, actor: Actor) -> list[WorkspaceView]:
        return [self._view(ws) for ws in await self._repo.list(owner_of(actor))]

    async def get(self, actor: Actor, workspace_id: UUID) -> WorkspaceView:
        return self._view(await self._load(actor, workspace_id))

    async def ready(self, actor: Actor, workspace_id: UUID) -> tuple[PackWorkspace, Path]:
        """Пространство, с файлами которого можно работать, и его папка паков."""
        ws = await self._load(actor, workspace_id)
        if ws.state is not WorkspaceState.ready:
            raise PackStudioError(PackStudioErrorCode.workspace_not_ready)
        return ws, self.packs_root(ws)

    async def protection(self, ws: PackWorkspace, root: Path) -> Protection:
        released = await asyncio.to_thread(self._released, ws, root)
        registries = await asyncio.to_thread(self._files.registries, root)
        return Protection(released=released, registries=registries)

    def packs_root(self, ws: PackWorkspace) -> Path:
        base = Path(ws.folder or "") if ws.kind is WorkspaceKind.folder else self._dirs(ws.id).tree
        return base if ws.packs_path == "." else base / ws.packs_path

    # ── изменения ────────────────────────────────────────────────────────────

    async def create(self, actor: Actor, inp: CreateWorkspaceInput) -> WorkspaceView:
        owner = owner_of(actor)
        if await self._repo.count(owner) >= self._max:
            raise PackStudioError(PackStudioErrorCode.workspace_limit, limit=self._max)
        if inp.kind is WorkspaceKind.folder:
            ws = await self._new_folder(owner, inp)
        else:
            ws, target = await self._new_git(owner, inp)
        await self._repo.add(ws)
        await self._record(actor, AUDIT_CREATE, ws)
        if ws.kind is WorkspaceKind.git:
            self._tasks.spawn(ws.id, lambda: self._clone(ws, target))
        return self._view(ws)

    async def refresh(self, actor: Actor, workspace_id: UUID) -> WorkspaceView:
        ws = await self._load(actor, workspace_id)
        if ws.kind is not WorkspaceKind.git:
            raise PackStudioError(PackStudioErrorCode.not_a_git_workspace)
        target = self._target(ws)
        if ws.state is WorkspaceState.ready:
            self._tasks.spawn(ws.id, lambda: self._fetch(ws, target))
            return self._view(ws)
        if self._tasks.is_busy(ws.id):
            raise PackStudioError(PackStudioErrorCode.workspace_busy)
        restarted = replace(ws, state=WorkspaceState.cloning, error=None, updated_at=_now())
        # Строка пишется до запуска: иначе быстрый клон успел бы записать `ready`, а эта запись вернула бы `cloning`.
        await self._repo.update(restarted)
        self._tasks.spawn(ws.id, lambda: self._clone(restarted, target))
        return self._view(restarted)

    async def delete(self, actor: Actor, workspace_id: UUID) -> None:
        ws = await self._load(actor, workspace_id)
        await self._tasks.cancel(ws.id)
        await self._repo.delete(ws.id, owner_of(actor))
        if ws.kind is WorkspaceKind.git:
            # Папку пользователя (`folder`) Студия не удаляет никогда: забывается только запись.
            await asyncio.to_thread(shutil.rmtree, self._workspaces_dir / str(ws.id), True)
        await self._record(actor, AUDIT_DELETE, ws)

    # ── создание ─────────────────────────────────────────────────────────────

    async def _new_folder(self, owner: str | None, inp: CreateWorkspaceInput) -> PackWorkspace:
        if not self._local:
            raise PackStudioError(PackStudioErrorCode.folder_not_allowed)
        folder = await asyncio.to_thread(self._checked_folder, inp.folder or "")
        packs_path = validate_packs_path(inp.packs_path) if inp.packs_path is not None else self._folder_packs(folder)
        root = folder if packs_path == "." else folder / packs_path
        if not root.is_dir():
            raise PackStudioError(PackStudioErrorCode.folder_unavailable)
        await asyncio.to_thread(self._files.check_packs_root, root)
        now = _now()
        return PackWorkspace(
            id=uuid4(),
            owner_id=owner,
            kind=WorkspaceKind.folder,
            label=_label(inp.label, folder.name or str(folder)),
            packs_path=packs_path,
            created_at=now,
            updated_at=now,
            folder=str(folder),
        )

    def _checked_folder(self, raw: str) -> Path:
        accepted = self._paths.accept(raw.strip())
        path = Path(accepted)
        if not raw.strip() or not path.is_absolute():
            raise PackStudioError(PackStudioErrorCode.folder_unavailable)
        try:
            folder = path.resolve(strict=True)
        except (OSError, RuntimeError):
            raise PackStudioError(PackStudioErrorCode.folder_unavailable) from None
        if not folder.is_dir() or (self._paths and self._paths.to_host(str(folder)) is None):
            raise PackStudioError(PackStudioErrorCode.folder_unavailable)
        return folder

    def _folder_packs(self, folder: Path) -> str:
        default = validate_packs_path(self._default_packs_path)
        return default if default != "." and (folder / default).is_dir() else "."

    async def _new_git(self, owner: str | None, inp: CreateWorkspaceInput) -> tuple[PackWorkspace, RemoteTarget]:
        self._policy.require_enabled()
        url = parse_remote_url(
            inp.url or "", allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        require_http_consent(url, insecure_http=inp.insecure_http, local_ok=self._policy.allow_local_remotes)
        if inp.credential_id is not None:
            credential = await self._credentials.get(inp.credential_id)
            if credential is None:
                raise git_error(GitErrorCode.credentials_missing)
            check_credential_matches(url, credential)
        packs_path = validate_packs_path(inp.packs_path if inp.packs_path is not None else self._default_packs_path)
        target = RemoteTarget(url=url, credential_id=inp.credential_id, insecure_http=inp.insecure_http)
        branch = await self._base_branch(target, inp.base_branch)
        now = _now()
        ws = PackWorkspace(
            id=uuid4(),
            owner_id=owner,
            kind=WorkspaceKind.git,
            label=_label(inp.label, _repo_label(url)),
            packs_path=packs_path,
            created_at=now,
            updated_at=now,
            state=WorkspaceState.cloning,
            remote_url=url.display_url,
            credential_id=inp.credential_id,
            insecure_http=inp.insecure_http,
            base_branch=branch,
        )
        return ws, target

    async def _base_branch(self, target: RemoteTarget, requested: str | None) -> str:
        """Ветка существует на сервере; без явной это ветка по умолчанию (HEAD сервера)."""
        branch = valid_branch(requested) if requested else None
        probe = await self._transport.probe(target)
        raise_probe_error(probe)
        if branch is not None:
            if branch not in probe.branches:
                raise git_error(GitErrorCode.branch_missing)
            return branch
        chosen = probe.default_branch or (probe.branches[0] if probe.branches else None)
        if chosen is None:
            raise git_error(GitErrorCode.branch_missing)
        return chosen

    # ── фоновые операции ─────────────────────────────────────────────────────

    async def _clone(self, ws: PackWorkspace, target: RemoteTarget) -> None:
        dirs = self._dirs(ws.id)
        branch = ws.base_branch or ""
        try:
            sha = await self._git.clone(dirs, target, branch=branch, packs_path=ws.packs_path, limits=self._limits)
            root = self.packs_root(ws)
            await asyncio.to_thread(self._files.measure, root, self._limits)
            await asyncio.to_thread(self._files.check_packs_root, root)
            released = await self._git.released(dirs, target, branch=branch, packs_path=ws.packs_path)
            await asyncio.to_thread(_save_released, dirs.root / _RELEASES_CACHE, released)
            now = _now()
            done = replace(ws, state=WorkspaceState.ready, base_sha=sha, fetched_at=now, error=None, updated_at=now)
        except (GitSyncError, PackStudioError) as exc:
            done = replace(ws, state=WorkspaceState.failed, error=_error_of(exc), updated_at=_now())
        except Exception as exc:  # noqa: BLE001 — фоновая задача: исход пишется в пространство, а не теряется
            logger.exception("pack studio: clone failed", workspace_id=str(ws.id))
            done = replace(ws, state=WorkspaceState.failed, error=_unexpected(exc), updated_at=_now())
        await self._repo.update(done)

    async def _fetch(self, ws: PackWorkspace, target: RemoteTarget) -> None:
        dirs = self._dirs(ws.id)
        branch = ws.base_branch or ""
        try:
            sha = await self._git.fetch(dirs, target, branch=branch, limits=self._limits)
            released = await self._git.released(dirs, target, branch=branch, packs_path=ws.packs_path)
            await asyncio.to_thread(_save_released, dirs.root / _RELEASES_CACHE, released)
            now = _now()
            done = replace(ws, base_sha=sha, fetched_at=now, error=None, updated_at=now)
        except (GitSyncError, PackStudioError) as exc:
            # Неудачная выборка не закрывает файлы: пространство остаётся готовым, ошибка видна в карточке.
            done = replace(ws, error=_error_of(exc), updated_at=_now())
        except Exception as exc:  # noqa: BLE001 — см. _clone
            logger.exception("pack studio: fetch failed", workspace_id=str(ws.id))
            done = replace(ws, error=_unexpected(exc), updated_at=_now())
        current = await self._repo.get(ws.id, ws.owner_id)
        if current is not None:
            await self._repo.update(
                replace(
                    current,
                    base_sha=done.base_sha,
                    fetched_at=done.fetched_at,
                    error=done.error,
                    updated_at=done.updated_at,
                )
            )

    # ── служебное ────────────────────────────────────────────────────────────

    async def _load(self, actor: Actor, workspace_id: UUID) -> PackWorkspace:
        ws = await self._repo.get(workspace_id, owner_of(actor))
        if ws is None:
            raise PackStudioError(PackStudioErrorCode.workspace_not_found)
        return ws

    def _view(self, ws: PackWorkspace) -> WorkspaceView:
        busy = self._tasks.is_busy(ws.id)
        if ws.state is WorkspaceState.cloning and not busy:
            # Процесс перезапустился посреди клона: продолжать некому, человек начинает заново «Обновить».
            interrupted = PackStudioError(PackStudioErrorCode.workspace_interrupted)
            ws = replace(ws, state=WorkspaceState.failed, error=_error_of(interrupted))
        display = self._paths.display(ws.folder) if ws.folder is not None else None
        return WorkspaceView(workspace=ws, busy=busy, folder_display=display)

    def _dirs(self, workspace_id: UUID) -> WorkspaceDirs:
        return self._dirs_factory(self._workspaces_dir / str(workspace_id))

    def _target(self, ws: PackWorkspace) -> RemoteTarget:
        url = parse_remote_url(
            ws.remote_url or "",
            allow_http=self._policy.allow_insecure_http,
            allow_local=self._policy.allow_local_remotes,
        )
        return RemoteTarget(url=url, credential_id=ws.credential_id, insecure_http=ws.insecure_http)

    def _released(self, ws: PackWorkspace, root: Path) -> ReleasedVersions:
        if ws.kind is WorkspaceKind.git:
            cached = _load_released(self._dirs(ws.id).root / _RELEASES_CACHE)
            if cached is not None:
                return cached
        # Папка, или кеш базы потерян: реестры рабочего дерева (оно начиналось с вершины базы).
        return self._files.released_on_disk(root)

    async def _record(self, actor: Actor, action: str, ws: PackWorkspace) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            action,
            actor_id=actor.id,
            target=str(ws.id),
            details={"kind": ws.kind.value, "label": ws.label, "url": ws.remote_url, "packs_path": ws.packs_path},
        )


def _label(raw: str | None, fallback: str) -> str:
    text = (raw or "").strip() or fallback
    return text[:LABEL_MAX]


def _repo_label(url: RemoteUrl) -> str:
    if url.owner and url.repo:
        return f"{url.owner}/{url.repo}"
    return url.repo or url.display_url


def _error_of(exc: GitSyncError | PackStudioError) -> WorkspaceError:
    return WorkspaceError(code=exc.code.value, detail=exc.detail)


def _unexpected(exc: Exception) -> WorkspaceError:
    return WorkspaceError(code=GitErrorCode.git_error.value, detail=type(exc).__name__)


def _save_released(path: Path, released: ReleasedVersions) -> None:
    body = {"sha": released.sha, "templates": {k: dict(v) for k, v in released.templates.items()}}
    path.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _load_released(path: Path) -> ReleasedVersions | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    raw = data.get("templates") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return None
    templates = {
        str(key): {str(v): str(d) for v, d in versions.items()}
        for key, versions in raw.items()
        if isinstance(versions, dict)
    }
    sha = data.get("sha")
    return ReleasedVersions(templates=templates, sha=sha if isinstance(sha, str) else None)
