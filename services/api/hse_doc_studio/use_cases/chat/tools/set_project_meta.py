from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.projects.update_project import UpdateProjectInput, UpdateProjectUC

_SPEC = ToolSpec(
    name="set_project_meta",
    description=(
        "Заполнить/обновить метаданные проекта (например тему работы, организацию, город, год) — "
        "пары ключ-значение, которые подставляются в титульные листы. Обновляются только переданные "
        "ключи, остальные сохраняются. Удобно для автозаполнения полей проекта."
    ),
    parameters={
        "type": "object",
        "properties": {
            "entries": {
                "type": "object",
                "description": 'Объект ключ→значение, напр. {"topic": "Разработка...", "year": "2026"}',
                "additionalProperties": {"type": "string"},
            }
        },
        "required": ["entries"],
    },
)


class SetProjectMetaTool:
    def __init__(self, update_project_uc: UpdateProjectUC) -> None:
        self._update_project = update_project_uc

    def definition(self) -> ToolDefinition:
        # Hidden from weak/local models: free-text metadata is easy for a small
        # model to hallucinate (it invented a topic/year nobody asked for). Strong
        # cloud models keep it for reliable field autofill.
        return ToolDefinition(spec=_SPEC, kind=ToolKind.write, handler=self, weak_model_safe=False)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        raw = args.get("entries")
        if not isinstance(raw, dict) or not raw:
            return ToolResult.error(
                "pass a non-empty entries object with key-value pairs"
                if lang == Lang.en
                else "передайте непустой объект entries с парами ключ-значение"
            )
        meta = {str(key): _as_text(value) for key, value in raw.items()}
        await self._update_project.execute(UpdateProjectInput(project_id=ctx.project_id, meta=meta))
        keys = ", ".join(sorted(meta.keys()))
        return ToolResult.ok(
            ("project metadata updated: " if lang == Lang.en else "обновлены метаданные проекта: ") + keys
        )


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else str(value)
