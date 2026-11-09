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
        "ключи, остальные сохраняются. unset удаляет ключи: поле возвращается к значению шаблона. "
        'Пример: {"entries": {"year": "2027"}, "unset": ["udc"]}'
    ),
    parameters={
        "type": "object",
        "properties": {
            "entries": {
                "type": "object",
                "description": 'Объект ключ→значение, напр. {"topic": "Разработка...", "year": "2026"}',
                "additionalProperties": {"type": "string"},
            },
            "unset": {
                "type": "array",
                "items": {"type": "string"},
                "description": 'Ключи, которые удалить из метаданных, напр. ["udc"]',
            },
        },
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
        raw_unset = args.get("unset")
        entries: dict[object, object] = raw if isinstance(raw, dict) else {}
        unset_keys: list[str] = (
            [k.strip() for k in raw_unset if isinstance(k, str) and k.strip()] if isinstance(raw_unset, list) else []
        )
        entries_ok = raw is None or isinstance(raw, dict)
        unset_ok = raw_unset is None or (isinstance(raw_unset, list) and len(unset_keys) == len(raw_unset))
        if not entries_ok or not unset_ok or not (entries or unset_keys):
            return ToolResult.error(
                "pass a non-empty entries object with key-value pairs or an unset list of keys"
                if lang == Lang.en
                else "передайте непустой объект entries с парами ключ-значение или список ключей unset"
            )
        meta = {str(key): _as_text(value) for key, value in entries.items()}
        unset = tuple(dict.fromkeys(unset_keys))
        both = sorted(set(meta) & set(unset))
        if both:
            return ToolResult.error(
                f"a key cannot be both set and unset: {', '.join(both)}"
                if lang == Lang.en
                else f"ключ нельзя одновременно задать и удалить: {', '.join(both)}"
            )
        await self._update_project.execute(
            UpdateProjectInput(project_id=ctx.project_id, meta=meta or None, meta_unset=unset)
        )
        parts = []
        if meta:
            label = "project metadata updated: " if lang == Lang.en else "обновлены метаданные проекта: "
            parts.append(label + ", ".join(sorted(meta)))
        if unset:
            label = "removed: " if lang == Lang.en else "удалены: "
            parts.append(label + ", ".join(unset))
        return ToolResult.ok("; ".join(parts))


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else str(value)
