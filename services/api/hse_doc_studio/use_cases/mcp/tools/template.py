"""Обновление проекта на новую версию шаблона: те же сценарии, что у окна «Обновить шаблон» в вебе.

Поток как в интерфейсе (`api/routers/v1/template_update.py`): статус (PROJECT_VIEW) показывает доступные версии,
план (TEMPLATE_MANAGE, dry-run) показывает, что станет с каждым файлом, и отдаёт отпечаток, применение
(TEMPLATE_MANAGE) исполняет ровно план с этим отпечатком. Права и запрет записи в проект «только для чтения»
проверяет `CallMcpToolUC` по таблице каталога, как гарды маршрутов. Конфликт без решения остаётся «моим», как
по умолчанию в окне. Перед записью сценарий сам делает снимок истории, поэтому обновление отменяется из истории.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.enums import ConflictResolution, Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.mcp.protocols import IMcpChangeAudit
from hse_doc_studio.core.template_update.entities import FileOp, TemplateUpdateRecord
from hse_doc_studio.core.template_update.errors import TemplateUpdateError
from hse_doc_studio.core.template_update.signature_presets import PresetPlace, SignaturePresetsPlan
from hse_doc_studio.core.vcs.errors import VcsError
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, McpTool, json_result, project_schema, text_arg
from hse_doc_studio.use_cases.template_update.apply_template_update import (
    ApplyTemplateUpdateInput,
    ApplyTemplateUpdateUC,
)
from hse_doc_studio.use_cases.template_update.get_template_update_status import (
    AvailableUpdate,
    GetTemplateUpdateStatusInput,
    GetTemplateUpdateStatusUC,
)
from hse_doc_studio.use_cases.template_update.plan_template_update import (
    PlanTemplateUpdateInput,
    PlanTemplateUpdateUC,
)

TEMPLATE_UPDATE_AUDIT_ACTION = "project.template_update"
_MAX_RESOLUTIONS = 500


def _notes(by_lang: Mapping[str, Sequence[str]]) -> list[str]:
    """Заметки на языке интерфейса, иначе по-русски, иначе по-английски (как `notesOf` в вебе)."""
    lang = current_interface_language().value
    for key in (lang, Lang.ru.value, Lang.en.value):
        if key in by_lang:
            return list(by_lang[key])
    return []


def _summary(version: TemplateVersion) -> str | None:
    lang = current_interface_language().value
    return version.summary.get(lang) or version.summary.get(Lang.ru.value) or version.summary.get(Lang.en.value)


def _version_view(version: TemplateVersion) -> dict[str, object]:
    return {
        "version": version.version,
        "released_at": version.released_at,
        "summary": _summary(version),
        "changes": _notes(version.changes),
        "breaking_changes": _notes(version.breaking_changes),
        "min_studio": version.min_studio,
    }


def _available_view(update: AvailableUpdate) -> dict[str, object]:
    return {"update_class": update.update_class, **_version_view(update.version)}


def _record_view(record: TemplateUpdateRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "from_version": record.from_version,
        "to_version": record.to_version,
        "at": record.at,
        "markers": list(record.markers),
        "reverted": record.reverted,
    }


def _op_view(op: FileOp) -> dict[str, object]:
    view: dict[str, object] = {"path": op.path, "action": op.action, "binary": op.binary}
    if op.doc_id is not None:
        view["doc_id"] = op.doc_id
    if op.needs_decision:
        view["conflicts"] = op.conflicts
        view["resolutions"] = [r.value for r in op.allowed_resolutions()]
    if op.approximate_base:
        view["approximate_base"] = True
    return view


def _place_view(place: PresetPlace) -> dict[str, object]:
    # `after_build`: место новой версии на якоре шаблона встанет по строке после сборки (signing-route.md, 15.17.10).
    return {"doc_id": place.doc_id, "slot_id": place.slot_id, "after_build": place.after_build}


def _presets_view(presets: SignaturePresetsPlan) -> dict[str, object]:
    """Пункт плана `signature_presets` (signing-route.md, 15.9), как в API."""
    return {
        "updated": [_place_view(p) for p in presets.updated],
        "kept": [{"doc_id": k.doc_id, "slot_id": k.slot_id, "reason": k.reason.value} for k in presets.kept],
    }


def _refusal(exc: Exception) -> ToolResult:
    """Отказ сценария обновления: текст уже локализован (план устарел, версия недоступна, идёт другое)."""
    return ToolResult.error(str(exc) or localized_error("Обновление шаблона не выполнено.", "Template update failed."))


def _resolutions(args: Mapping[str, object]) -> dict[str, ConflictResolution]:
    raw = args.get("resolutions")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or len(raw) > _MAX_RESOLUTIONS:
        raise ArgumentError(
            localized_error(
                "resolutions: объект {путь: mine|theirs|markers}", "resolutions: an object {path: mine|theirs|markers}"
            )
        )
    try:
        return {str(path): ConflictResolution(str(value)) for path, value in raw.items()}
    except ValueError as exc:
        raise ArgumentError(
            localized_error(f"Неизвестное решение конфликта: {exc}", f"Unknown conflict resolution: {exc}")
        ) from None


class TemplateUpdateStatusTool(McpTool):
    spec = ToolSpec(
        name="template_update_status",
        description=(
            "Версия шаблона проекта и доступные обновления: класс (patch, minor, major), что нового и что ломает. "
            "Например current_version 2026.1.1, recommended 2026.1.2 (patch). Что обновление сделает с файлами, "
            "покажет plan_template_update."
        ),
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        status = await (await self._deps.get(GetTemplateUpdateStatusUC)).execute(
            GetTemplateUpdateStatusInput(project_id=ctx.project_id)
        )
        lock = status.project.lock
        return json_result(
            {
                "pack_id": lock.pack_id,
                "template_id": lock.template_id,
                "current_version": lock.version,
                "current": _version_view(status.current) if status.current is not None else None,
                "available": [_available_view(u) for u in status.available],
                "recommended": _available_view(status.recommended) if status.recommended is not None else None,
                "last_update": _record_view(status.last_update) if status.last_update is not None else None,
                "unresolved_markers": status.unresolved_markers,
                "in_progress": status.in_progress,
                "digest_mismatch": status.digest_mismatch,
            }
        )


class PlanTemplateUpdateTool(McpTool):
    spec = ToolSpec(
        name="plan_template_update",
        description=(
            "Предпросмотр обновления шаблона до версии to_version: что станет с каждым файлом (update, add, delete, "
            "merge, conflict), какие места подписей из шаблона перейдут на новую версию (signature_presets) и "
            "отпечаток плана для apply_template_update. Файлы проекта не меняются. Например "
            'to_version: "2026.1.2".'
        ),
        parameters=project_schema(
            {"to_version": {"type": "string", "description": "Версия из template_update_status, например 2026.1.2"}},
            ("to_version",),
        ),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        to_version = text_arg(args, "to_version")
        try:
            planned = await (await self._deps.get(PlanTemplateUpdateUC)).execute(
                PlanTemplateUpdateInput(project_id=ctx.project_id, to_version=to_version)
            )
        except (TemplateUpdateError, VcsError) as exc:
            return _refusal(exc)
        plan = planned.planned.plan
        return json_result(
            {
                "from_version": plan.from_version,
                "to_version": plan.to_version,
                "update_class": plan.update_class,
                "fingerprint": plan.fingerprint,
                "provenance": plan.provenance,
                "counts": {action.value: count for action, count in plan.counts.items()},
                "files": [_op_view(op) for op in plan.ops],
                "warnings": [{"code": w.code, "doc_ids": list(w.doc_ids)} for w in plan.warnings],
                "signature_presets": _presets_view(plan.signature_presets),
                "hint": localized_error(
                    "Конфликт без решения в resolutions остаётся как есть (mine). theirs берёт файл шаблона, "
                    "markers пишет слияние с маркерами конфликта. signature_presets.updated: места подписей, "
                    "которые встанут как в новой версии шаблона; kept не обновятся: manual изменены автором, "
                    "route документ на подписании, signed над зафиксированным PDF есть ЭП. Пустой files при "
                    "непустом updated значит, что файлы не меняются, а места обновятся. after_build: место встанет "
                    "по строке шаблона после следующей сборки документа.",
                    "A conflict without a decision in resolutions stays as is (mine). theirs takes the template "
                    "file, markers writes the merge with conflict markers. signature_presets.updated: signature "
                    "places that will move to the new template version; kept will not: manual changed by the "
                    "author, route the document is on a signing route, signed the frozen PDF has an e-signature. "
                    "Empty files with a non-empty updated means no files change but the places will. after_build: "
                    "the place follows the template line after the next build of the document.",
                ),
            }
        )


class ApplyTemplateUpdateTool(McpTool):
    spec = ToolSpec(
        name="apply_template_update",
        description=(
            "Применить обновление шаблона, как кнопка «Обновить» в окне предпросмотра: ровно план из "
            "plan_template_update с его fingerprint. Перед записью делается снимок истории. Конфликты решает "
            'resolutions, по умолчанию «моё». Например to_version: "2026.1.2", fingerprint из плана, '
            'resolutions: {"report/report.tex": "theirs"}.'
        ),
        parameters=project_schema(
            {
                "to_version": {"type": "string", "description": "Версия из плана, например 2026.1.2"},
                "fingerprint": {"type": "string", "description": "fingerprint из ответа plan_template_update"},
                "resolutions": {
                    "type": "object",
                    "description": "Решения по конфликтным файлам: путь -> mine, theirs или markers",
                    "additionalProperties": {"type": "string", "enum": [r.value for r in ConflictResolution]},
                },
            },
            ("to_version", "fingerprint"),
        ),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        inp = ApplyTemplateUpdateInput(
            project_id=ctx.project_id,
            to_version=text_arg(args, "to_version"),
            fingerprint=text_arg(args, "fingerprint"),
            resolutions=_resolutions(args),
        )
        try:
            result = await (await self._deps.get(ApplyTemplateUpdateUC)).execute(inp)
        except (TemplateUpdateError, VcsError) as exc:
            return _refusal(exc)
        record = result.record
        audit = await self._deps.get(IMcpChangeAudit)  # type: ignore[type-abstract]  # порт из контейнера
        await audit.record(
            TEMPLATE_UPDATE_AUDIT_ACTION,
            target=str(ctx.project_id),
            details={
                "via": "mcp",
                "fields": ["template_version"],
                "update_id": record.id,
                "from_version": record.from_version,
                "to_version": record.to_version,
                "written": len(result.written),
                "deleted": len(result.deleted),
                "markers": len(result.markers),
                "signature_places": len(result.signature_places),
            },
        )
        return json_result(
            {
                "update": _record_view(record),
                "written": result.written,
                "deleted": result.deleted,
                "markers": result.markers,
                "signature_places": [_place_view(p) for p in result.signature_places],
                "hint": localized_error(
                    "Готово. В файлах из markers остались маркеры конфликта, их нужно разрешить вручную. Отменить "
                    "обновление можно в настройках проекта или откатом к снимку истории.",
                    "Done. Files in markers still have conflict markers to resolve by hand. The update can be "
                    "undone in the project settings or by restoring the history snapshot.",
                ),
            }
        )
