"""Каталоги паков (docs/design/template-studio.md, 10.3 и 10.4, срез T17): источники, «Проверить», «Применить».

Источник это git (адрес, папка паков, тег, ветка или sha, доступ), загруженный архив или папка (только локально).
«Проверить» раскладывает ревизию во временную папку, разбирает её лоадером этой Студии в отдельном процессе
(`pack_lint`, `releases check`, дайджесты) и строит план: какие версии появятся, какие уже есть, какие не для этой
Студии и что мешает применить. Разложенная ревизия остаётся до «Применить», которое берёт ровно её (по номеру
ревизии), заново сверяет план со свежим каталогом и кладёт версии в хранилище по дайджесту. Каталог переключается
атомарно, без рестарта: этот процесс перечитывает его сразу, остальные замечают новую ревизию сами.

Права: на сервере только админ установки, локально человек Студии. Каждое действие пишется в историю источника и
(на сервере) в журнал аудита. Отслеживание раз в сутки проверяет источники git с галочкой и применяет новые
выпущенные версии, если план чистый.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.access.context import current_actor, set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import PackOriginKind
from hse_doc_studio.core.git_sync.credential_match import check_credential_matches
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.core.pack_catalog.entities import (
    CatalogEvent,
    CatalogSource,
    EventAction,
    SourceError,
    SourceKind,
)
from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode
from hse_doc_studio.core.pack_catalog.plan import CatalogPlan, ExistingPack, plan_catalog
from hse_doc_studio.core.pack_catalog.protocols import (
    IArchiveStore,
    ICatalogAudit,
    ICatalogSourceRepository,
    ICatalogStore,
    IRevisionInspector,
    IRevisionStager,
    StagedRevision,
    StageLimits,
)
from hse_doc_studio.core.pack_catalog.store import CatalogState
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.core.pack_studio.git_flow import repo_key, repo_path_of
from hse_doc_studio.core.pack_studio.paths import validate_packs_path
from hse_doc_studio.core.pack_studio.protocols import IServiceAccessRepository
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.git_sync.probe_remote import require_http_consent, valid_branch

logger = structlog.get_logger()

AUDIT_ADD = "pack_catalog.source_add"
AUDIT_UPDATE = "pack_catalog.source_update"
AUDIT_REMOVE = "pack_catalog.source_remove"
AUDIT_ENABLE = "pack_catalog.source_enable"
AUDIT_DISABLE = "pack_catalog.source_disable"
AUDIT_CHECK = "pack_catalog.check"
AUDIT_APPLY = "pack_catalog.apply"
AUDIT_TRACK = "pack_catalog.track"

LABEL_MAX = 120
REF_MAX = 200
HISTORY_LIMIT = 50
# Отслеживание: источник проверяется не чаще раза в сутки.
TRACK_EVERY = timedelta(hours=23)
_CHECKED = "checked"
_NEXT = "next"
_META = "checked.json"


@dataclass(frozen=True)
class SourceInput:
    """Поля источника при создании и правке; None в правке значит «не менять»."""

    label: str | None = None
    url: str | None = None
    packs_path: str | None = None
    ref: str | None = None
    credential_id: UUID | None = None
    service_access_id: UUID | None = None
    insecure_http: bool | None = None
    replace_builtin: bool | None = None
    track: bool | None = None
    # Правка: явно убрать доступ (личный и служебный).
    clear_access: bool = False


@dataclass(frozen=True)
class CatalogVersionView:
    template: str
    version: str
    listed: bool


@dataclass(frozen=True)
class CatalogPackView:
    """Пак каталога: откуда, виден ли мастеру и какие версии лежат в хранилище."""

    id: str
    name: Mapping[str, str]
    origin_kind: str
    source_id: str | None
    listed: bool
    replaces_builtin: bool
    versions: tuple[CatalogVersionView, ...]


@dataclass(frozen=True)
class SourceView:
    source: CatalogSource
    busy: bool
    packs: tuple[CatalogPackView, ...]


@dataclass(frozen=True)
class CatalogOverview:
    revision: int
    sources: tuple[SourceView, ...]
    # Вшитые паки (и паки удалённых источников): что уже есть в каталоге помимо подключённых.
    packs: tuple[CatalogPackView, ...]


@dataclass(frozen=True)
class CheckView:
    source: CatalogSource
    plan: CatalogPlan


@dataclass(frozen=True)
class ApplyView:
    source: CatalogSource
    plan: CatalogPlan
    added: tuple[str, ...]
    catalog_revision: int


def _now() -> datetime:
    return datetime.now(UTC)


def _label(raw: str | None, fallback: str) -> str:
    text = (raw or "").strip() or fallback
    if len(text) > LABEL_MAX:
        raise CatalogError(CatalogErrorCode.label_invalid)
    return text


def _ref(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if len(text) > REF_MAX:
        raise ValueError("ref is too long")
    return valid_branch(text)


def _summary(plan: CatalogPlan) -> dict[str, Any]:
    return {
        "new": plan.new_count,
        "blockers": [b.value for b in plan.blockers],
        "packs": [p.id for p in plan.packs],
    }


class PackCatalogService:
    def __init__(  # noqa: PLR0913 — порты сценария и пределы развёртывания
        self,
        sources: ICatalogSourceRepository,
        stager: IRevisionStager,
        inspector: IRevisionInspector,
        store: ICatalogStore,
        templates: ITemplateRepository,
        archives: IArchiveStore,
        policy: GitSyncPolicy,
        *,
        work_dir: Path,
        limits: StageLimits,
        app_version: str | None,
        local_mode: bool,
        audit: ICatalogAudit | None = None,
        credentials: IGitCredentialRepository | None = None,
        service_access: IServiceAccessRepository | None = None,
    ) -> None:
        self._sources = sources
        self._stager = stager
        self._inspector = inspector
        self._store = store
        self._templates = templates
        self._archives = archives
        self._policy = policy
        self._work_dir = work_dir
        self._limits = limits
        self._app_version = app_version
        self._local = local_mode
        self._audit = audit
        self._credentials = credentials
        self._service_access = service_access
        self._busy: set[UUID] = set()

    @property
    def limits(self) -> StageLimits:
        return self._limits

    def upload_path(self) -> Path:
        return self._archives.upload_path()

    # ── чтение ───────────────────────────────────────────────────────────────

    async def overview(self, actor: Actor) -> CatalogOverview:
        self._require(actor)
        sources = await self._sources.list()
        state = self._store.state()
        views = tuple(SourceView(s, s.id in self._busy, self._packs_of(state, str(s.id))) for s in sources)
        alive = {str(s.id) for s in sources}
        others = tuple(
            view
            for pack in self._templates.list_packs()
            if (view := self._pack_view(pack.id, state)) is not None
            and (view.origin_kind == PackOriginKind.builtin.value or view.source_id not in alive)
        )
        return CatalogOverview(revision=state.revision, sources=views, packs=others)

    async def source(self, actor: Actor, source_id: UUID) -> SourceView:
        self._require(actor)
        source = await self._load(source_id)
        return SourceView(source, source.id in self._busy, self._packs_of(self._store.state(), str(source.id)))

    async def history(self, actor: Actor, source_id: UUID) -> list[CatalogEvent]:
        self._require(actor)
        await self._load(source_id)
        return await self._sources.events(source_id, limit=HISTORY_LIMIT)

    async def find_folder_source(self, actor: Actor, workspace_id: UUID) -> CatalogSource | None:
        self._require(actor)
        return next((s for s in await self._sources.list() if s.workspace_id == workspace_id), None)

    # ── источники ────────────────────────────────────────────────────────────

    async def add_git(self, actor: Actor, inp: SourceInput) -> CatalogSource:
        self._require(actor)
        self._policy.require_enabled()
        url = parse_remote_url(
            inp.url or "", allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        require_http_consent(url, insecure_http=bool(inp.insecure_http), local_ok=self._policy.allow_local_remotes)
        await self._check_access(url.display_url, inp.credential_id, inp.service_access_id)
        now = _now()
        source = CatalogSource(
            id=uuid4(),
            kind=SourceKind.git,
            label=_label(inp.label, url.display_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")),
            created_at=now,
            updated_at=now,
            created_by=actor.id,
            replace_builtin=bool(inp.replace_builtin),
            track=bool(inp.track),
            packs_path=_packs_path(inp.packs_path, default="packs"),
            url=url.display_url,
            ref=_ref(inp.ref),
            credential_id=inp.credential_id,
            service_access_id=inp.service_access_id,
            insecure_http=bool(inp.insecure_http),
        )
        await self._sources.add(source)
        await self._record(actor, AUDIT_ADD, EventAction.add, source, details={"url": source.url, "ref": source.ref})
        return source

    async def add_archive(self, actor: Actor, upload: Path, *, name: str, inp: SourceInput) -> CatalogSource:
        self._require(actor)
        digest = await asyncio.to_thread(self._archives.save, upload, name=name)
        now = _now()
        source = CatalogSource(
            id=uuid4(),
            kind=SourceKind.archive,
            label=_label(inp.label, Path(name).name or "archive"),
            created_at=now,
            updated_at=now,
            created_by=actor.id,
            replace_builtin=bool(inp.replace_builtin),
            packs_path=_packs_path(inp.packs_path, default="."),
            archive_digest=digest,
            archive_name=Path(name).name[:LABEL_MAX] or None,
        )
        await self._sources.add(source)
        await self._record(
            actor, AUDIT_ADD, EventAction.add, source, details={"archive": digest, "name": source.archive_name}
        )
        return source

    async def replace_archive(self, actor: Actor, source_id: UUID, upload: Path, *, name: str) -> CatalogSource:
        self._require(actor)
        source = await self._load(source_id)
        if source.kind is not SourceKind.archive:
            upload.unlink(missing_ok=True)
            raise CatalogError(CatalogErrorCode.source_kind_not_allowed)
        digest = await asyncio.to_thread(self._archives.save, upload, name=name)
        updated = _unchecked(
            replace(source, archive_digest=digest, archive_name=Path(name).name[:LABEL_MAX] or None, updated_at=_now())
        )
        await self._sources.update(updated)
        await self._record(
            actor, AUDIT_UPDATE, EventAction.update, updated, details={"archive": digest, "name": updated.archive_name}
        )
        return updated

    async def add_folder(
        self, actor: Actor, *, folder: str, packs_path: str, label: str, workspace_id: UUID | None
    ) -> CatalogSource:
        """Локально: папка рабочего пространства Студии шаблонов («Подключить к каталогу этой Студии»)."""
        self._require(actor)
        if not self._local:
            raise CatalogError(CatalogErrorCode.source_kind_not_allowed)
        if workspace_id is not None and await self.find_folder_source(actor, workspace_id) is not None:
            raise CatalogError(CatalogErrorCode.source_exists)
        now = _now()
        source = CatalogSource(
            id=uuid4(),
            kind=SourceKind.folder,
            label=_label(label, Path(folder).name or folder),
            created_at=now,
            updated_at=now,
            created_by=actor.id,
            packs_path=_packs_path(packs_path, default="."),
            folder=folder,
            workspace_id=workspace_id,
        )
        await self._sources.add(source)
        await self._record(actor, AUDIT_ADD, EventAction.add, source, details={"folder": folder})
        return source

    async def update(self, actor: Actor, source_id: UUID, inp: SourceInput) -> CatalogSource:
        self._require(actor)
        source = await self._load(source_id)
        changed = replace(
            source,
            label=_label(inp.label, source.label) if inp.label is not None else source.label,
            replace_builtin=source.replace_builtin if inp.replace_builtin is None else inp.replace_builtin,
            track=(source.track if inp.track is None else inp.track) and source.kind is SourceKind.git,
            packs_path=_packs_path(inp.packs_path, default=source.packs_path)
            if inp.packs_path is not None
            else source.packs_path,
            ref=_ref(inp.ref) if inp.ref is not None and source.kind is SourceKind.git else source.ref,
        )
        if source.kind is SourceKind.git and (
            inp.clear_access or inp.credential_id is not None or inp.service_access_id is not None
        ):
            await self._check_access(source.url or "", inp.credential_id, inp.service_access_id)
            changed = replace(changed, credential_id=inp.credential_id, service_access_id=inp.service_access_id)
        if changed == source:
            return source
        moved = (changed.ref, changed.packs_path, changed.replace_builtin) != (
            source.ref,
            source.packs_path,
            source.replace_builtin,
        )
        updated = replace(_unchecked(changed) if moved else changed, updated_at=_now())
        await self._sources.update(updated)
        await self._record(
            actor,
            AUDIT_UPDATE,
            EventAction.update,
            updated,
            details={
                "label": updated.label,
                "ref": updated.ref,
                "packs_path": updated.packs_path,
                "replace_builtin": updated.replace_builtin,
                "track": updated.track,
            },
        )
        return updated

    async def set_enabled(self, actor: Actor, source_id: UUID, enabled: bool) -> CatalogSource:
        """Выключение прячет паки источника из мастера проекта; версии остаются для проектов (10.4)."""
        self._require(actor)
        source = await self._load(source_id)
        if source.enabled == enabled:
            return source
        async with self._exclusive(source.id):
            await asyncio.to_thread(self._store.set_listed, str(source.id), listed=enabled)
            updated = replace(source, enabled=enabled, updated_at=_now())
            await self._sources.update(updated)
        action, event = (AUDIT_ENABLE, EventAction.enable) if enabled else (AUDIT_DISABLE, EventAction.disable)
        await self._record(actor, action, event, updated, details={"label": updated.label})
        return updated

    async def remove(self, actor: Actor, source_id: UUID) -> None:
        """Источник уходит, его паки скрываются из мастера, версии в хранилище остаются для проектов."""
        self._require(actor)
        source = await self._load(source_id)
        async with self._exclusive(source.id):
            await asyncio.to_thread(self._store.set_listed, str(source.id), listed=False)
            await self._sources.delete(source.id)
            await asyncio.to_thread(shutil.rmtree, self._work_dir / str(source.id), True)
        await self._record(actor, AUDIT_REMOVE, EventAction.remove, source, details={"label": source.label})

    # ── проверить и применить ────────────────────────────────────────────────

    async def check(self, actor: Actor, source_id: UUID) -> CheckView:
        self._require(actor)
        source = await self._load(source_id)
        async with self._exclusive(source.id):
            try:
                staged, plan = await self._stage_and_plan(source, keep=True)
            except (CatalogError, GitSyncError, PackStudioError) as exc:
                failed = await self._failed(source, exc)
                await self._record(actor, AUDIT_CHECK, EventAction.check, failed, ok=False, details=_error(exc))
                raise
            checked = replace(
                source,
                checked_revision=staged.revision,
                checked_at=_now(),
                check_ok=plan.ok,
                pending_versions=plan.new_count,
                error=None,
            )
            await self._sources.update(checked)
        await self._record(
            actor, AUDIT_CHECK, EventAction.check, checked, ok=plan.ok, revision=staged.revision, details=_summary(plan)
        )
        return CheckView(checked, plan)

    async def apply(self, actor: Actor, source_id: UUID, revision: str) -> ApplyView:
        self._require(actor)
        source = await self._load(source_id)
        if not source.enabled:
            raise CatalogError(CatalogErrorCode.source_disabled)
        if source.checked_revision is None:
            raise CatalogError(CatalogErrorCode.not_checked)
        async with self._exclusive(source.id):
            try:
                staged, plan = await self._staged_plan(source, revision)
                applied = await asyncio.to_thread(self._store.apply, source, plan, staged.root)
            except (CatalogError, GitSyncError, PackStudioError) as exc:
                await self._record(
                    actor, AUDIT_APPLY, EventAction.apply, source, ok=False, revision=revision, details=_error(exc)
                )
                raise
            done = replace(
                source,
                applied_revision=staged.revision,
                applied_at=_now(),
                checked_revision=staged.revision,
                check_ok=True,
                pending_versions=0,
                error=None,
                updated_at=_now(),
            )
            await self._sources.update(done)
            await asyncio.to_thread(shutil.rmtree, self._work_dir / str(source.id), True)
        await self._record(
            actor,
            AUDIT_APPLY,
            EventAction.apply,
            done,
            revision=staged.revision,
            details={"added": list(applied.added), "catalog_revision": applied.state.revision},
        )
        return ApplyView(done, plan, applied.added, applied.state.revision)

    async def track_due(self) -> int:
        """Отслеживание (раз в сутки): источники git с галочкой проверяются, новые выпущенные версии применяются,
        если план чистый. Идёт от имени админа, который подключил источник (его доступ git). Возвращает, сколько
        источников получили новые версии."""
        applied = 0
        for source in await self._sources.list():
            if not (source.track and source.enabled and source.kind is SourceKind.git):
                continue
            if source.checked_at is not None and _now() - source.checked_at < TRACK_EVERY:
                continue
            if await self._track_one(source):
                applied += 1
        return applied

    async def _track_one(self, source: CatalogSource) -> bool:
        actor = self._owner_actor(source)
        previous = current_actor()
        set_current_actor(actor)
        try:
            return await self._track_as(actor, source)
        except (CatalogError, GitSyncError, PackStudioError) as exc:
            logger.warning("pack catalog: tracking failed", source=str(source.id), code=getattr(exc, "code", None))
            return False
        finally:
            set_current_actor(previous)

    async def _track_as(self, actor: Actor, source: CatalogSource) -> bool:
        view = await self.check(actor, source.id)
        if not view.plan.ok or view.plan.new_count == 0:
            return False
        result = await self.apply(actor, source.id, view.plan.revision)
        await self._record(
            actor,
            AUDIT_TRACK,
            EventAction.track,
            result.source,
            revision=result.plan.revision,
            details={"added": list(result.added)},
        )
        return True

    def _owner_actor(self, source: CatalogSource) -> Actor:
        if self._local or source.created_by is None:
            return Actor.local()
        return Actor.user(source.created_by, is_instance_admin=True)

    async def _stage_and_plan(self, source: CatalogSource, *, keep: bool) -> tuple[StagedRevision, CatalogPlan]:
        base = self._work_dir / str(source.id)
        staged = await self._stager.stage(source, base / _NEXT, self._limits)
        plan = await self._plan(source, staged)
        if keep:
            staged = await asyncio.to_thread(_keep_checked, base, staged)
        return staged, plan

    async def _staged_plan(self, source: CatalogSource, revision: str) -> tuple[StagedRevision, CatalogPlan]:
        """Ревизия, которую проверяли: разложенная при проверке, или та же самая, разложенная заново."""
        base = self._work_dir / str(source.id)
        kept = await asyncio.to_thread(_load_checked, base)
        if kept is not None and kept.revision == revision:
            return kept, await self._plan(source, kept)
        if source.checked_revision != revision:
            raise CatalogError(CatalogErrorCode.revision_moved, expected=revision, actual=source.checked_revision)
        staged, plan = await self._stage_and_plan(source, keep=False)
        if staged.revision != revision:
            raise CatalogError(CatalogErrorCode.revision_moved, expected=revision, actual=staged.revision)
        return staged, plan

    async def _plan(self, source: CatalogSource, staged: StagedRevision) -> CatalogPlan:
        tree = await self._inspector.inspect(staged.root)
        sources = await self._sources.list()
        alive = {str(s.id) for s in sources}
        existing = {
            pack.id: ExistingPack(
                origin=pack.origin,
                source_alive=pack.origin.kind is PackOriginKind.builtin or pack.origin.source_id in alive,
            )
            for pack in self._templates.list_packs()
        }
        return plan_catalog(
            tree,
            revision=staged.revision,
            source_id=str(source.id),
            replace_builtin=source.replace_builtin,
            existing=existing,
            existing_digest=self._templates.content_digest,
            app_version=self._app_version,
            labels={str(s.id): s.label for s in sources},
        )

    # ── служебное ────────────────────────────────────────────────────────────

    def _require(self, actor: Actor) -> None:
        if self._local:
            return
        require_admin(actor)

    async def _load(self, source_id: UUID) -> CatalogSource:
        source = await self._sources.get(source_id)
        if source is None:
            raise CatalogError(CatalogErrorCode.source_not_found)
        return source

    async def _check_access(self, url: str, credential_id: UUID | None, service_access_id: UUID | None) -> None:
        parsed = parse_remote_url(
            url, allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        if credential_id is not None and service_access_id is not None:
            raise ValueError("choose either a personal or a service access")
        if credential_id is not None:
            credential = await self._credentials.get(credential_id) if self._credentials is not None else None
            if credential is None:
                raise git_error(GitErrorCode.credentials_missing)
            check_credential_matches(parsed, credential)
        if service_access_id is not None:
            access = await self._service_access.get(service_access_id) if self._service_access is not None else None
            key = repo_key(parsed.host, parsed.port, repo_path_of(parsed.display_url, None)) if parsed.host else None
            if access is None or access.repo_key != key:
                raise git_error(GitErrorCode.credentials_missing)

    @contextlib.asynccontextmanager
    async def _exclusive(self, source_id: UUID) -> AsyncIterator[None]:
        """Одна проверка или применение на источник в процессе; между процессами их разводит замок хранилища и
        сверка ревизии перед записью."""
        if source_id in self._busy:
            raise CatalogError(CatalogErrorCode.source_busy)
        self._busy.add(source_id)
        try:
            yield
        finally:
            self._busy.discard(source_id)

    async def _failed(self, source: CatalogSource, exc: Exception) -> CatalogSource:
        code = getattr(exc, "code", None)
        detail = getattr(exc, "detail", None) or str(exc)
        failed = replace(
            source,
            checked_at=_now(),
            check_ok=False,
            error=SourceError(str(getattr(code, "value", code) or "error"), str(detail)[:500]),
        )
        await self._sources.update(failed)
        return failed

    async def _record(  # noqa: PLR0913 — событие истории и аудита одной записью
        self,
        actor: Actor,
        audit_action: str,
        action: EventAction,
        source: CatalogSource,
        *,
        ok: bool = True,
        revision: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        summary = dict(details or {})
        await self._sources.add_event(
            CatalogEvent(
                id=uuid4(),
                source_id=source.id,
                action=action,
                at=_now(),
                ok=ok,
                actor_id=actor.id,
                revision=revision,
                summary=summary,
            )
        )
        if self._audit is not None:
            await self._audit.record(
                audit_action,
                actor_id=actor.id,
                target=str(source.id),
                details={"kind": source.kind.value, "label": source.label, "ok": ok, "revision": revision, **summary},
            )

    def _packs_of(self, state: CatalogState, source_id: str) -> tuple[CatalogPackView, ...]:
        return tuple(
            view
            for pack in state.packs
            if pack.source_id == source_id and (view := self._pack_view(pack.id, state)) is not None
        )

    def _pack_view(self, pack_id: str, state: CatalogState) -> CatalogPackView | None:
        info = next((p for p in self._templates.list_packs() if p.id == pack_id), None)
        stored = state.pack(pack_id)
        if info is None and stored is None:
            return None
        if stored is not None and (info is None or info.origin.kind is not PackOriginKind.subscribed):
            # Пак источника выключен и уступил вшитому, или каталог ещё не перечитан: показываем хранилище.
            versions = tuple(
                CatalogVersionView(t.id, v.version, v.listed and stored.listed)
                for t in stored.templates
                for v in t.versions
            )
            return CatalogPackView(
                id=pack_id,
                name=info.name if info is not None else {},
                origin_kind=PackOriginKind.subscribed.value,
                source_id=stored.source_id,
                listed=stored.listed,
                replaces_builtin=stored.replace_builtin,
                versions=versions,
            )
        assert info is not None  # noqa: S101 — оба None отсечены выше
        versions = tuple(
            CatalogVersionView(t.id, v, v not in t.hidden_versions)
            for t in info.templates
            for v in sorted(self._templates.list_versions(pack_id, t.id))
        )
        return CatalogPackView(
            id=pack_id,
            name=info.name,
            origin_kind=info.origin.kind.value,
            source_id=info.origin.source_id,
            listed=info.listed,
            replaces_builtin=info.origin.replaces_builtin,
            versions=versions,
        )


def _packs_path(raw: str | None, *, default: str) -> str:
    return validate_packs_path(raw if raw is not None else default)


def _unchecked(source: CatalogSource) -> CatalogSource:
    """Источник изменился: прежняя проверка больше не про него."""
    return replace(source, checked_revision=None, checked_at=None, check_ok=None, pending_versions=0)


def _error(exc: Exception) -> dict[str, Any]:
    code = getattr(exc, "code", None)
    return {"error": str(getattr(code, "value", code) or type(exc).__name__)}


def _keep_checked(base: Path, staged: StagedRevision) -> StagedRevision:
    """Разложенная ревизия остаётся до «Применить»: `next` становится `checked`, номер ревизии рядом."""
    checked = base / _CHECKED
    if checked.exists():
        shutil.rmtree(checked)
    (base / _NEXT).rename(checked)
    rel = staged.root.relative_to(base / _NEXT)
    (base / _META).write_text(json.dumps({"revision": staged.revision, "root": rel.as_posix()}), encoding="utf-8")
    return StagedRevision(revision=staged.revision, root=checked / rel)


def _load_checked(base: Path) -> StagedRevision | None:
    try:
        meta = json.loads((base / _META).read_text(encoding="utf-8"))
        root = (base / _CHECKED / str(meta["root"])).resolve()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not root.is_dir() or not root.is_relative_to((base / _CHECKED).resolve()):
        return None
    return StagedRevision(revision=str(meta["revision"]), root=root)
