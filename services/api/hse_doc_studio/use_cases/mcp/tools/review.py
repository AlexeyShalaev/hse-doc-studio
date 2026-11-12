"""Ревью-комментарии (только сервер). Сценарии ревью сами проверяют право COMMENT и автора."""

from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.review.entities import Anchor, PdfAnchor, ReviewThread, ThreadStatus
from hse_doc_studio.use_cases.mcp.tools._base import (
    ArgumentError,
    McpTool,
    json_result,
    optional_text,
    project_schema,
    text_arg,
)
from hse_doc_studio.use_cases.review.threads import (
    CreateReviewThreadUC,
    ListReviewThreadsUC,
    NewThread,
    ReplyReviewThreadUC,
    SetReviewThreadStatusUC,
)

_THREAD = {"type": "string", "description": "Идентификатор обсуждения"}
_STATUS = {"type": "string", "enum": [s.value for s in ThreadStatus]}


def _status(raw: str | None) -> ThreadStatus | None:
    if raw is None:
        return None
    try:
        return ThreadStatus(raw)
    except ValueError:
        raise ArgumentError(f"status: {raw!r}") from None


def _anchor_view(thread: ReviewThread) -> dict[str, object]:
    """Тред из превью PDF без находки в исходнике привязан к месту в PDF: документ, страница и выделенный текст."""
    anchor = thread.anchor
    if isinstance(anchor, PdfAnchor):
        return {"kind": "pdf", "quote": anchor.text, "doc_id": anchor.doc_id, "page": anchor.page}
    return {"kind": "text", "quote": anchor.quote}


def _view(thread: ReviewThread) -> dict[str, object]:
    return {
        "id": thread.id,
        "path": thread.path,
        **_anchor_view(thread),
        "status": thread.status,
        "created_by": thread.created_by_name,
        "created_at": thread.created_at,
        "resolved_by": thread.resolved_by_name,
        "comments": [
            {"id": c.id, "author": c.author_name, "body": c.body, "created_at": c.created_at} for c in thread.comments
        ],
    }


class ListReviewThreadsTool(McpTool):
    spec = ToolSpec(
        name="list_review_threads",
        description=(
            "Обсуждения ревью в проекте: цитата, файл, статус и комментарии. Фильтры path и status. "
            "kind=text: цитата из исходника path; kind=pdf: комментарий к месту в PDF документа doc_id "
            "(страница page, quote это выделенный текст PDF, path это сам PDF)."
        ),
        parameters=project_schema({"path": {"type": "string"}, "status": _STATUS}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        threads = await (await self._deps.get(ListReviewThreadsUC)).execute(
            ctx.project_id, path=optional_text(args, "path"), status=_status(optional_text(args, "status"))
        )
        return json_result([_view(t) for t in threads])


class CreateReviewThreadTool(McpTool):
    spec = ToolSpec(
        name="create_review_thread",
        description=(
            "Оставить комментарий ревью к фрагменту файла. quote: точная цитата из файла (по ней комментарий "
            "привязывается к тексту), prefix и suffix: немного текста до и после для однозначности. "
            "Комментарий к тексту из PDF оставляйте по исходнику: найдите фрагмент через grep_project или read_tex, "
            "он появится и в редакторе, и в превью."
        ),
        parameters=project_schema(
            {
                "path": {"type": "string"},
                "quote": {"type": "string"},
                "prefix": {"type": "string"},
                "suffix": {"type": "string"},
                "body": {"type": "string", "description": "Текст комментария"},
            },
            ("path", "quote", "body"),
        ),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        anchor = Anchor(
            quote=text_arg(args, "quote"),
            prefix=optional_text(args, "prefix") or "",
            suffix=optional_text(args, "suffix") or "",
        )
        thread = await (await self._deps.get(CreateReviewThreadUC)).execute(
            ctx.project_id, NewThread(path=text_arg(args, "path"), anchor=anchor, body=text_arg(args, "body"))
        )
        return json_result(_view(thread))


class ReplyReviewThreadTool(McpTool):
    spec = ToolSpec(
        name="reply_review_thread",
        description="Ответить в обсуждении ревью.",
        parameters=project_schema({"thread_id": _THREAD, "body": {"type": "string"}}, ("thread_id", "body")),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        thread = await (await self._deps.get(ReplyReviewThreadUC)).execute(
            ctx.project_id, text_arg(args, "thread_id"), text_arg(args, "body")
        )
        return json_result(_view(thread))


class SetReviewThreadStatusTool(McpTool):
    spec = ToolSpec(
        name="set_review_thread_status",
        description="Закрыть (resolved) или переоткрыть (open) обсуждение ревью.",
        parameters=project_schema({"thread_id": _THREAD, "status": _STATUS}, ("thread_id", "status")),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        status = _status(text_arg(args, "status"))
        assert status is not None  # noqa: S101 — text_arg не пропускает пустое
        thread = await (await self._deps.get(SetReviewThreadStatusUC)).execute(
            ctx.project_id, text_arg(args, "thread_id"), status
        )
        return json_result(_view(thread))
