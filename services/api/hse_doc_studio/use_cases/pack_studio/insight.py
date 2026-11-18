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
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.entities import (
    DiagnosticCheck,
    DiagnosticSeverity,
    LintScope,
    PackDiagnostic,
    PackEditorHints,
    PackLintReport,
)
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.core.pack_studio.outcome.lint import LintFinding
from hse_doc_studio.core.pack_studio.paths import VersionRef, validate_rel_path, version_ref_of
from hse_doc_studio.core.pack_studio.protocols import IPackInspector
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

MAX_PARALLEL_CHECKS = 2
# Статические правила результата ждём не дольше этого: находки `pack_lint` не должны ждать разбора версии.
OUTCOME_STATIC_TIMEOUT_S = 5.0
MAX_DIAGNOSTICS = 500


class StaticOutcomeLint(Protocol):
    """Статические правила линтера результата версии (`PackOutcomeLintService.static`)."""

    async def static(
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str
    ) -> tuple[LintFinding, ...]: ...


def outcome_diagnostics(version_dir: str, findings: tuple[LintFinding, ...], *, released: bool) -> list[PackDiagnostic]:
    """Находки линтера результата в общий список «Проблемы»: информация не показывается, ошибка выпущенной версии
    (она неизменна) это предупреждение, как у схемы."""
    found: list[PackDiagnostic] = []
    for item in findings:
        if item.severity == "info":
            continue
        error = item.severity == "error" and not released
        found.append(
            PackDiagnostic(
                DiagnosticSeverity.error if error else DiagnosticSeverity.warning,
                DiagnosticCheck.outcome,
                f"[{item.rule_id}] {item.message}",
                path=f"{version_dir}/{item.file}" if item.file else None,
                line=item.line,
                pointer=item.pointer,
            )
        )
    return found


class PackInsightService:
    def __init__(
        self, workspaces: PackWorkspaceService, inspector: IPackInspector, outcome: StaticOutcomeLint | None = None
    ) -> None:
        self._workspaces = workspaces
        self._inspector = inspector
        self._outcome = outcome
        self._slots = asyncio.Semaphore(MAX_PARALLEL_CHECKS)

    async def lint(self, actor: Actor, workspace_id: UUID, raw_path: str) -> PackLintReport:
        path = validate_rel_path(raw_path)
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref_of(path)
        if ref is not None:
            async with self._slots:
                protection = await self._workspaces.protection(ws, root)
                released = protection.released.is_released(ref.pack, ref.template, ref.version)
                findings = await asyncio.to_thread(self._inspector.lint_version, root, ref.dir, released=released)
            extra = await self._outcome_findings(actor, workspace_id, ref, released=released)
            return PackLintReport(LintScope.version, ref.dir, released, (*findings, *extra)[:MAX_DIAGNOSTICS])
        async with self._slots:
            checked = await asyncio.to_thread(self._inspector.check_manifest, root, path)
        if checked is None:
            return PackLintReport(LintScope.none, None, False, ())
        return PackLintReport(LintScope.file, path, False, checked)

    async def _outcome_findings(
        self, actor: Actor, workspace_id: UUID, ref: VersionRef | None, *, released: bool
    ) -> list[PackDiagnostic]:
        """Статические правила результата к находкам версии. Версия, которую вычислитель не прочитал (причину уже
        назвал `pack_lint`), или долгий разбор: без этих находок, а не отказ всей проверки."""
        if ref is None or self._outcome is None:
            return []
        try:
            found = await asyncio.wait_for(
                self._outcome.static(actor, workspace_id, ref.pack, ref.template, ref.version),
                OUTCOME_STATIC_TIMEOUT_S,
            )
        except (PackStudioError, TimeoutError):
            return []
        return outcome_diagnostics(ref.dir, found, released=released)

    async def hints(self, actor: Actor, workspace_id: UUID, raw_path: str) -> PackEditorHints:
        path = validate_rel_path(raw_path)
        _, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref_of(path)
        if ref is None:
            return PackEditorHints(version=None)
        return await asyncio.to_thread(self._inspector.hints, root, ref.dir)
