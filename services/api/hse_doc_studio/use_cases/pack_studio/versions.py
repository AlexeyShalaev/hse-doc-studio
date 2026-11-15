"""Мастер «Новая версия» Студии шаблонов (docs/design/template-studio.md, раздел 7, 4.3 и 4.5; срез T10).

- «Новая версия» на шаблоне: база по умолчанию последняя выпущенная, каталог копируется в черновик `beta`.
- Живой класс черновика по классификатору при каждом запросе состояния (интерфейс спрашивает после каждой правки),
  номер по классу, заметки `changes` ru и en с черновиком из отчёта.
- Новый номер черновика: класс поднят или номер выпустили в базе раньше (4.3).
- «Перенести правки в новую версию»: каталог выпущенной версии отличается от выпуска (7.3). Правки копируются в
  черновик, у git каталог выпущенной возвращается к базе, реестр рабочего дерева берёт записи базы.
- «Выпустить»: у git сначала выборка базы (номер мог уже уйти), затем `freeze` с `status: stable`, `released_at`,
  `release.kind` и по желанию `default_version`. Это правки рабочей ветки: выпущенной версия станет после слияния PR
  (D10), до него выпуск можно повторить (запись своей версии заменяется).

Выпущенные версии берутся из той же защиты, что у записи файлов: реестры базовой ветки у git, реестры на диске у
папки. Шаги, которые пишут файлы, идут под замком пространства (`workspace_busy` второй, как у git).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.pack_studio.entities import PackWorkspace, WorkspaceKind
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import (
    RELEASES_FILE,
    TEMPLATES_DIR,
    VersionRef,
    template_key,
    validate_rel_path,
)
from hse_doc_studio.core.pack_studio.protocols import IPackVersions, IPackWorkspaceGit
from hse_doc_studio.core.pack_studio.versions import (
    BaseRegistry,
    CreatedVersion,
    MovedVersion,
    NewVersionOptions,
    ReleasedVersionView,
    TemplateRef,
    VersionNotesInput,
    VersionState,
)
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE
from hse_doc_studio.use_cases.pack_studio.preview import version_ref
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

_T = TypeVar("_T")


def _today() -> date:
    return datetime.now(DISPLAY_ZONE).date()


def template_ref(pack: str, template: str) -> TemplateRef:
    path = validate_rel_path(f"{pack}/{TEMPLATES_DIR}/{template}")
    parts = path.split("/")
    if len(parts) != 3:  # noqa: PLR2004 — пак, templates, шаблон
        raise PackStudioError(PackStudioErrorCode.path_not_allowed)
    return TemplateRef(parts[0], parts[2])


@dataclass(frozen=True)
class CreateVersionInput:
    base: str | None = None
    version: str | None = None
    update_class: TemplateUpdateClass | None = None


@dataclass(frozen=True)
class ReleaseInput:
    kind: TemplateUpdateClass | None = None
    set_default: bool = False


class PackVersionService:
    def __init__(
        self,
        workspaces: PackWorkspaceService,
        versions: IPackVersions,
        git: IPackWorkspaceGit,
        *,
        today: Callable[[], date] = _today,
    ) -> None:
        self._workspaces = workspaces
        self._versions = versions
        self._git = git
        self._today = today

    # ── чтение ───────────────────────────────────────────────────────────────

    async def options(self, actor: Actor, workspace_id: UUID, pack: str, template: str) -> NewVersionOptions:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = template_ref(pack, template)
        registry = await self._registry(ws, root, ref, with_text=False)
        return await asyncio.to_thread(self._versions.options, root, ref, registry)

    async def state(self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str) -> VersionState:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)
        registry = await self._registry(ws, root, _template_of(ref), with_text=False)
        return await asyncio.to_thread(self._versions.state, root, ref, registry)

    # ── шаги ─────────────────────────────────────────────────────────────────

    async def create(
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, inp: CreateVersionInput
    ) -> CreatedVersion:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = template_ref(pack, template)

        async def work() -> CreatedVersion:
            registry = await self._registry(ws, root, ref, with_text=False)
            return await asyncio.to_thread(
                lambda: self._versions.create(
                    root,
                    ref,
                    base=inp.base,
                    to=inp.version,
                    update_class=inp.update_class,
                    registry=registry,
                    today=self._today(),
                )
            )

        return await self._locked(ws, work)

    async def save_notes(  # noqa: PLR0913 — путь версии и заметки
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str, notes: VersionNotesInput
    ) -> VersionState:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)

        async def work() -> VersionState:
            await self._check_draft(ws, root, ref)
            await asyncio.to_thread(self._versions.save_notes, root, ref, notes)
            registry = await self._registry(ws, root, _template_of(ref), with_text=False)
            return await asyncio.to_thread(self._versions.state, root, ref, registry)

        return await self._locked(ws, work)

    async def renumber(  # noqa: PLR0913 — путь версии и номер
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str, to: str
    ) -> MovedVersion:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)
        target = version_ref(pack, template, to)

        async def work() -> MovedVersion:
            await self._check_draft(ws, root, ref)
            registry = await self._registry(ws, root, _template_of(ref), with_text=False)
            return await asyncio.to_thread(self._versions.renumber, root, ref, target.version, registry, self._today())

        return await self._locked(ws, work)

    async def move_edits(  # noqa: PLR0913 — путь версии и номер
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str, to: str | None
    ) -> MovedVersion:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)
        number = version_ref(pack, template, to).version if to else None

        async def work() -> MovedVersion:
            registry = await self._registry(ws, root, _template_of(ref), with_text=True)
            moved = await asyncio.to_thread(self._versions.move_edits, root, ref, number, registry, self._today())
            if ws.kind is not WorkspaceKind.git:
                return moved
            await self._git.restore_from_base(
                self._workspaces.dirs_of(ws),
                self._workspaces.target_of(ws),
                base_branch=ws.base_branch or "",
                paths=[self._repo_path(ws, ref.dir)],
            )
            return MovedVersion(
                ref=moved.ref, previous=moved.previous, unreleased=moved.unreleased, restored=True, edited=moved.edited
            )

        return await self._locked(ws, work)

    async def release(  # noqa: PLR0913 — путь версии и выбор выпуска
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str, inp: ReleaseInput
    ) -> ReleasedVersionView:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)

        async def work() -> ReleasedVersionView:
            fresh = await self._workspaces.fetch_base(ws) if ws.kind is WorkspaceKind.git else ws
            registry = await self._registry(fresh, root, _template_of(ref), with_text=True)
            if ref.version in registry.versions:
                await self._raise_released(root, ref, registry)
            return await asyncio.to_thread(
                lambda: self._versions.release(
                    root,
                    ref,
                    kind=inp.kind,
                    set_default=inp.set_default,
                    registry=registry,
                    today=self._today(),
                )
            )

        return await self._locked(ws, work)

    # ── служебное ────────────────────────────────────────────────────────────

    async def _locked(self, ws: PackWorkspace, work: Callable[[], Awaitable[_T]]) -> _T:
        return await self._workspaces.tasks.exclusive(ws.id, work)

    async def _check_draft(self, ws: PackWorkspace, root: Path, ref: VersionRef) -> None:
        """Черновик правится, выпущенная в базе версия только база для копии (4.5, 7.3)."""
        protection = await self._workspaces.protection(ws, root)
        protection.check_write(ref.dir)

    async def _raise_released(self, root: Path, ref: VersionRef, registry: BaseRegistry) -> None:
        """Номер уже выпущен в базе: свой же выпуск после слияния или чужой раньше (4.3)."""
        state = await asyncio.to_thread(self._versions.state, root, ref, registry)
        if not state.modified:
            raise PackStudioError(PackStudioErrorCode.version_released, path=ref.dir)
        raise PackStudioError(
            PackStudioErrorCode.version_taken, version=ref.version, suggested=state.move_to, released_in_base=True
        )

    async def _registry(self, ws: PackWorkspace, root: Path, ref: TemplateRef, *, with_text: bool) -> BaseRegistry:
        protection = await self._workspaces.protection(ws, root)
        versions = dict(protection.released.templates.get(template_key(ref.pack, ref.template), {}))
        if ws.kind is not WorkspaceKind.git:
            return BaseRegistry(versions=versions)
        text = None
        if with_text:
            path = self._repo_path(ws, f"{ref.dir}/{RELEASES_FILE}")
            texts = await self._git.base_registries(
                self._workspaces.dirs_of(ws),
                self._workspaces.target_of(ws),
                base_branch=ws.base_branch or "",
                paths=[path],
            )
            text = texts.get(path)
        return BaseRegistry(versions=versions, text=text, from_git=True)

    @staticmethod
    def _repo_path(ws: PackWorkspace, path: str) -> str:
        return path if ws.packs_path == "." else f"{ws.packs_path}/{path}"


def _template_of(ref: VersionRef) -> TemplateRef:
    return TemplateRef(ref.pack, ref.template)
