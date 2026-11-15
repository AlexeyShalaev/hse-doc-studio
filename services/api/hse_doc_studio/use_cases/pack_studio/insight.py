"""Проверки и подсказки редактора Студии шаблонов (docs/design/template-studio.md, 4.4 и 5.4; срез T8).

- `lint`: для файла внутри версии это `pack_lint` всей версии и схемы её манифестов (находки разложены по файлам и
  строкам), для `pack.yaml`, `template.yaml` и `releases.yaml` схема этого файла, для прочего ничего. Выпущенность
  версии берётся из той же защиты, что у записи (D10): у выпущенной ошибки схемы это предупреждения.
- `hints`: поля анкеты версии и макросы `\\hse...` её динамических инклудов для автодополнения `.j2` и `.tex`.

Проверка идёт в процессе и без TeX (Jinja только разбирается, песочница T3); одновременно не больше двух, чтобы
частые сохранения не заняли все потоки.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.entities import LintScope, PackEditorHints, PackLintReport
from hse_doc_studio.core.pack_studio.paths import validate_rel_path, version_ref_of
from hse_doc_studio.core.pack_studio.protocols import IPackInspector
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

MAX_PARALLEL_CHECKS = 2


class PackInsightService:
    def __init__(self, workspaces: PackWorkspaceService, inspector: IPackInspector) -> None:
        self._workspaces = workspaces
        self._inspector = inspector
        self._slots = asyncio.Semaphore(MAX_PARALLEL_CHECKS)

    async def lint(self, actor: Actor, workspace_id: UUID, raw_path: str) -> PackLintReport:
        path = validate_rel_path(raw_path)
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref_of(path)
        async with self._slots:
            if ref is not None:
                protection = await self._workspaces.protection(ws, root)
                released = protection.released.is_released(ref.pack, ref.template, ref.version)
                findings = await asyncio.to_thread(self._inspector.lint_version, root, ref.dir, released=released)
                return PackLintReport(LintScope.version, ref.dir, released, findings)
            checked = await asyncio.to_thread(self._inspector.check_manifest, root, path)
        if checked is None:
            return PackLintReport(LintScope.none, None, False, ())
        return PackLintReport(LintScope.file, path, False, checked)

    async def hints(self, actor: Actor, workspace_id: UUID, raw_path: str) -> PackEditorHints:
        path = validate_rel_path(raw_path)
        _, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref_of(path)
        if ref is None:
            return PackEditorHints(version=None)
        return await asyncio.to_thread(self._inspector.hints, root, ref.dir)
