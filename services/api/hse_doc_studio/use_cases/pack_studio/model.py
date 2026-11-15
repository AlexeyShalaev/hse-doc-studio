"""Формы версии шаблона: модель, точечные правки манифестов, операции на несколько файлов (срезы T11 и T12).

Путь правки тот же, что у ручной (docs/design/template-studio.md, 5.0): запись под замком пространства с `If-Match`
по ETag файла, защита выпущенной версии (`version_released`), точечные правки YAML (D11). Сверх того правка формы не
пишется, если у файла появилась новая находка лоадера или схемы (`model_invalid`). После записи клиент, как и после
ручной правки, перезапускает «Проблемы», живой класс версии (T10) и предпросмотр.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.model import (
    MAX_MODEL_OPS,
    FileChange,
    LibraryDocument,
    ModelAction,
    ModelEditError,
    VersionModel,
)
from hse_doc_studio.core.pack_studio.paths import VERSION_MANIFEST, VersionRef
from hse_doc_studio.core.pack_studio.protocols import IPackVersionModel, IYamlEditor
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService, YamlOp, apply_yaml_ops
from hse_doc_studio.use_cases.pack_studio.preview import version_ref
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

# Файлы, которые правит форма: манифест версии и манифесты документов (от каталога версии).
_MODEL_FILE = re.compile(r"^(version\.yaml|files/[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*/doc\.yaml)$")


@dataclass(frozen=True)
class ModelView:
    ref: VersionRef
    # Почему версию нельзя менять (`version_released`); None: можно.
    read_only: str | None
    model: VersionModel
    # Файлы, которые записала или удалила правка (пусто у чтения): клиент перечитывает открытые.
    changed: tuple[str, ...] = ()


class PackModelService:
    def __init__(
        self,
        workspaces: PackWorkspaceService,
        files: PackFilesService,
        model: IPackVersionModel,
        yaml_editor: IYamlEditor,
    ) -> None:
        self._workspaces = workspaces
        self._files = files
        self._model = model
        self._yaml = yaml_editor

    async def get(self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str) -> ModelView:
        ref = version_ref(pack, template, version)
        return await self._view(actor, workspace_id, ref, ())

    async def library(self, actor: Actor, workspace_id: UUID) -> tuple[LibraryDocument, ...]:
        _, root = await self._workspaces.ready(actor, workspace_id)
        return await asyncio.to_thread(self._model.library, root)

    async def patch(  # noqa: PLR0913 — путь версии, файл, правки и версия файла
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        file: str,
        ops: Sequence[YamlOp],
        if_match: str | None,
    ) -> ModelView:
        if not 0 < len(ops) <= MAX_MODEL_OPS:
            raise PackStudioError(PackStudioErrorCode.model_invalid, reason=f"1..{MAX_MODEL_OPS} operations")
        if not _MODEL_FILE.match(file):
            raise PackStudioError(PackStudioErrorCode.model_invalid, reason="file must be version.yaml or a doc.yaml")
        ref = version_ref(pack, template, version)
        _, root = await self._workspaces.ready(actor, workspace_id)

        def edit(text: str) -> str:
            edited = apply_yaml_ops(self._yaml, text, ops)
            try:
                self._model.check_edit(root, ref.dir, file, text, edited)
            except ModelEditError as exc:
                raise PackStudioError(PackStudioErrorCode.model_invalid, reason=str(exc)[:300]) from None
            return edited

        written = await self._files.edit_yaml(actor, workspace_id, f"{ref.dir}/{file}", edit, if_match)
        return await self._view(actor, workspace_id, ref, (written.path,))

    async def act(  # noqa: PLR0913 — путь версии, операция и версия манифеста
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        action: ModelAction,
        if_match: str | None,
    ) -> ModelView:
        ref = version_ref(pack, template, version)

        def plan(root: Path) -> tuple[FileChange, ...]:
            try:
                return self._model.plan(root, ref.dir, action)
            except ModelEditError as exc:
                raise PackStudioError(PackStudioErrorCode.model_invalid, reason=str(exc)[:300]) from None
            except (TypeError, ValueError) as exc:
                raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None

        manifest = f"{ref.dir}/{VERSION_MANIFEST}"
        changes = await self._files.apply_changes(actor, workspace_id, manifest, if_match, plan)
        return await self._view(actor, workspace_id, ref, tuple(c.path for c in changes))

    async def _view(self, actor: Actor, workspace_id: UUID, ref: VersionRef, changed: tuple[str, ...]) -> ModelView:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        protection = await self._workspaces.protection(ws, root)
        reason = protection.read_only_reason(f"{ref.dir}/{VERSION_MANIFEST}")
        try:
            model = await asyncio.to_thread(self._model.describe, root, ref.dir)
        except (TypeError, ValueError) as exc:
            raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None
        return ModelView(ref, reason.value if reason is not None else None, model, changed)
