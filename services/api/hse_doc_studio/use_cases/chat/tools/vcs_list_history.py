from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.vcs.entities import VcsCommit
from hse_doc_studio.use_cases.vcs.list_vcs_history import ListVcsHistoryInput, ListVcsHistoryUC

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

_SPEC = ToolSpec(
    name="vcs_list_history",
    description=(
        "Лента версий проекта (служебный git): последние снимки с идентификатором, типом "
        "(создание/правка/сборка/снимок/откат), сообщением и датой. Можно ограничить документом."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": f"Сколько версий вернуть (по умолчанию {_DEFAULT_LIMIT})."},
            "doc_id": {
                "type": "string",
                "description": (
                    "Ограничить историю одним документом по его id, напр. 'thesis' "
                    "(в командном проекте — id инстанса, напр. 'vkr--ivanov')."
                ),
            },
        },
    },
)

_KIND_RU = {
    "init": "создание",
    "edit": "правка",
    "compile": "сборка",
    "manual": "снимок",
    "restore": "откат",
}

_KIND_EN = {
    "init": "init",
    "edit": "edit",
    "compile": "build",
    "manual": "snapshot",
    "restore": "restore",
}


class VcsListHistoryTool:
    def __init__(self, list_history_uc: ListVcsHistoryUC) -> None:
        self._uc = list_history_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        raw_limit = args.get("limit")
        limit = int(raw_limit) if isinstance(raw_limit, (int, float)) else _DEFAULT_LIMIT
        limit = max(1, min(limit, _MAX_LIMIT))
        doc_id = args.get("doc_id")
        doc_id_str = doc_id if isinstance(doc_id, str) and doc_id else None
        lang = current_interface_language()
        out = await self._uc.execute(ListVcsHistoryInput(project_id=ctx.project_id, doc_id=doc_id_str, limit=limit))
        if not out.commits:
            return ToolResult.ok("version history is empty" if lang == Lang.en else "история версий пуста")
        header = "Versions (newest first):\n" if lang == Lang.en else "Версии (новые сверху):\n"
        return ToolResult.ok(header + "\n".join(_fmt(c, lang) for c in out.commits))


def _fmt(commit: VcsCommit, lang: Lang) -> str:
    kinds = _KIND_EN if lang == Lang.en else _KIND_RU
    kind = kinds.get(commit.kind.value, commit.kind.value)
    return f"- {commit.short_id} [{kind}] {commit.message} ({commit.created_at.isoformat()})"
