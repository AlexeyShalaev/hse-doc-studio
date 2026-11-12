"""Сдача и подписи. Пакет сдачи собирает тул агента package_project; подписать можно только комплект целиком
(sign_submission, опасный тул с правом токена `sign`), отдельный слот не выставляется."""

from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.plan import SignaturePlan
from hse_doc_studio.use_cases.mcp.tools._base import (
    McpTool,
    bool_arg,
    json_result,
    optional_text,
    project_schema,
    text_arg,
)
from hse_doc_studio.use_cases.signatures.get_signature_plan import GetSignaturePlanInput, GetSignaturePlanUC
from hse_doc_studio.use_cases.signatures.get_signatures import GetSignaturesInput, GetSignaturesUC
from hse_doc_studio.use_cases.signatures.sign_submission import (
    SigningConflictError,
    SignSubmissionInput,
    SignSubmissionUC,
)
from hse_doc_studio.use_cases.submission.get_submission_profiles import (
    GetSubmissionProfilesInput,
    GetSubmissionProfilesUC,
)
from hse_doc_studio.use_cases.submission.list_submissions import ListSubmissionsInput, ListSubmissionsUC


class ListSubmissionProfilesTool(McpTool):
    spec = ToolSpec(
        name="list_submission_profiles",
        description="Профили сдачи проекта (куда и какой комплект документов сдаётся) для package_project.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(GetSubmissionProfilesUC)).execute(
            GetSubmissionProfilesInput(project_id=ctx.project_id)
        )
        return json_result(out.profiles)


class ListSubmissionsTool(McpTool):
    spec = ToolSpec(
        name="list_submissions",
        description="Собранные пакеты сдачи: когда, по какому профилю, размер.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(ListSubmissionsUC)).execute(ListSubmissionsInput(project_id=ctx.project_id))
        return json_result(
            [{"record": i.record, "size_bytes": i.size_bytes, "profile_name": i.profile_name} for i in out.items]
        )


class ListSignaturesTool(McpTool):
    spec = ToolSpec(
        name="list_signatures",
        description="Состояние подписей документов: какие слоты подписаны, какие ждут, устаревшие заморозки.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(GetSignaturesUC)).execute(GetSignaturesInput(project_id=ctx.project_id))
        return json_result({"state": out.state, "stale_frozen": out.stale_frozen, "plate_outdated": out.plate_outdated})


def _plan_json(plan: SignaturePlan) -> dict[str, object]:
    """План для модели: счётчик, по слоту кто, каким способом, в каком статусе и чего не хватает."""
    return {
        "profile_id": plan.profile_id,
        "signed": plan.signed,
        "total": plan.total,
        "waiting_for_me": plan.waiting_for_me,
        # Необязательные неподписанные (signing-route.md, 13.10): в `total` их нет, как и пропущенных.
        "optional_pending": plan.optional_pending,
        "docs": [
            {
                "doc_id": doc.doc_id,
                "frozen_sha256": doc.frozen.sha256 if doc.frozen else None,
                "signed_sha256": doc.frozen.signed_sha256 if doc.frozen and doc.frozen.signed_sha256 else None,
                # Версия на подписи маршрута (signing-route.md, 12.4) и расхождение с ней рабочей сборки.
                "pinned": {"sha256": doc.pinned.sha256, "pinned_at": doc.pinned.pinned_at} if doc.pinned else None,
                "working_differs": doc.working_differs,
                "slots": [
                    {
                        "slot_id": s.slot_id,
                        "signer": s.signer.name or s.signer.persona,
                        "method": s.state.method.value,
                        "crypto": s.state.crypto,
                        "status": s.status.value,
                        "reason": s.state.reason.value if s.state.reason else None,
                        "hint": s.hint,
                        "is_mine": s.is_mine,
                        "optional": s.optional,
                        "skipped": {"at": s.skipped.at, "route_id": s.skipped.route_id} if s.skipped else None,
                        "check": {
                            "format": s.state.check.format,
                            "verdict": s.state.check.verdict.value,
                            "signer": s.state.check.signer,
                        }
                        if s.state.check
                        else None,
                    }
                    for s in doc.slots
                ],
            }
            for doc in plan.docs
        ],
    }


class GetSignaturePlanTool(McpTool):
    spec = ToolSpec(
        name="get_signature_plan",
        description=(
            "План подписей по профилю сдачи или документу: «подписано k из n», по каждому слоту подписант, способ "
            "(картинка, открепленная ЭП, PAdES), статус и чего не хватает."
        ),
        parameters=project_schema(
            {
                "profile_id": {"type": "string", "description": "Профиль сдачи (list_submission_profiles)"},
                "doc_id": {"type": "string", "description": "Документ; без него весь профиль или проект"},
                "author": {"type": "string", "description": "Командный проект: слаг автора, чей комплект"},
            }
        ),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        plan = await (await self._deps.get(GetSignaturePlanUC)).execute(
            GetSignaturePlanInput(
                project_id=ctx.project_id,
                profile_id=optional_text(args, "profile_id"),
                author=optional_text(args, "author"),
                doc_id=optional_text(args, "doc_id"),
            )
        )
        return json_result(_plan_json(plan))


class SignSubmissionTool(McpTool):
    spec = ToolSpec(
        name="sign_submission",
        description=(
            "Подписать комплект профиля сдачи от имени владельца токена его ключом по умолчанию: зафиксировать PDF, "
            "если нужно, и подписать все его слоты его способом. Ключ с паролем через MCP не подписывает. "
            "Если фиксация сбросит уже поставленные подписи, нужен confirm_reset. Документ, который идёт по "
            "маршруту подписания, не фиксируется и подписывается только в очередь владельца токена на подпись; "
            "иначе он пропускается с причиной «Документ на подписании по маршруту»."
        ),
        parameters=project_schema(
            {
                "profile_id": {"type": "string", "description": "Профиль сдачи"},
                "author": {"type": "string", "description": "Командный проект: слаг автора, чей комплект"},
                "confirm_reset": {
                    "type": "boolean",
                    "description": "Подтвердить сброс уже поставленных подписей при повторной фиксации",
                },
            },
            required=("profile_id",),
        ),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        # Право токена `sign` проверяет вызов тула (McpToolRule.scope), до прав на проект.
        uc = await self._deps.get(SignSubmissionUC)
        inp = SignSubmissionInput(
            project_id=ctx.project_id,
            profile_id=text_arg(args, "profile_id"),
            author=optional_text(args, "author"),
            confirm_reset=bool_arg(args, "confirm_reset", default=False),
        )
        preview = await uc.preview(inp)
        if preview.key is None:
            return ToolResult.error(
                localized_error(
                    "Нет ключа подписи по умолчанию: выберите его в настройках Студии",
                    "No default signing key: choose one in the Studio settings",
                )
            )
        if preview.key.protected:
            return ToolResult.error(
                localized_error(
                    "Ключ защищён паролем, подпишите в интерфейсе Студии",
                    "The key is passphrase-protected, sign in the Studio interface",
                )
            )
        # Подписывается ровно то, что показал этот предпросмотр: пересборка между ним и подписью даёт отказ.
        inp.expected = {doc.doc_id: doc.token for doc in preview.docs}
        try:
            out = await uc.execute(inp)
        except SigningConflictError as exc:
            return ToolResult.error(str(exc))
        plan = await (await self._deps.get(GetSignaturePlanUC)).execute(
            GetSignaturePlanInput(project_id=ctx.project_id, profile_id=inp.profile_id, author=inp.author)
        )
        return json_result(
            {
                "key": preview.key.label,
                "frozen_docs": list(out.frozen_docs),
                "results": [
                    {"doc_id": r.doc_id, "slot_id": r.slot_id, "ok": r.ok, "message": r.message} for r in out.results
                ],
                "plan": _plan_json(plan),
            }
        )
