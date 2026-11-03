"""Готовые сценарии (prompts MCP): клиент подставляет их в диалог, дальше модель работает тулами Студии."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode


@dataclass(frozen=True)
class McpPromptArgument:
    name: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class McpPrompt:
    name: str
    description: str
    arguments: tuple[McpPromptArgument, ...]
    template_ru: str
    template_en: str

    def render(self, args: Mapping[str, str]) -> str:
        missing = [a.name for a in self.arguments if a.required and not (args.get(a.name) or "").strip()]
        if missing:
            raise McpError(McpErrorCode.invalid_arguments, ", ".join(missing))
        values = {a.name: (args.get(a.name) or "").strip() for a in self.arguments}
        return localized_error(self.template_ru, self.template_en).format(**values)


_PROJECT = McpPromptArgument("project_id", "UUID проекта / project UUID")
_DOC = McpPromptArgument("doc_id", "Документ, напр. vkr / document id, e.g. vkr")

MCP_PROMPTS: tuple[McpPrompt, ...] = (
    McpPrompt(
        name="fix_build",
        description="Собрать документ и исправить ошибки сборки / Build a document and fix build errors",
        arguments=(_PROJECT, _DOC),
        template_ru=(
            "Проект {project_id}, документ {doc_id}. Собери его инструментом compile_document. Если сборка упала, "
            "по хвосту лога найди причину, прочитай нужный файл (read_tex), исправь его точечно (edit_tex) и "
            "собери снова. Повторяй, пока сборка не пройдёт, но не больше пяти попыток. В конце коротко перечисли, "
            "что исправил."
        ),
        template_en=(
            "Project {project_id}, document {doc_id}. Build it with compile_document. If the build fails, find the "
            "cause in the log tail, read the file (read_tex), fix it with a targeted edit (edit_tex) and build "
            "again. Repeat until the build passes, at most five attempts. Finally list what you fixed."
        ),
    ),
    McpPrompt(
        name="normcontrol",
        description="Разобрать замечания нормоконтроля и исправить их / Go through normcontrol findings and fix them",
        arguments=(_PROJECT, _DOC),
        template_ru=(
            "Проект {project_id}, документ {doc_id}. Получи замечания проверок (list_check_findings; если сборки "
            "нет, сначала compile_document). Сгруппируй их по смыслу, исправь в исходниках то, что исправляется "
            "правкой текста, затем пересобери и покажи, сколько замечаний осталось и почему."
        ),
        template_en=(
            "Project {project_id}, document {doc_id}. Get the check findings (list_check_findings; if there is no "
            "build yet, run compile_document first). Group them, fix in the sources whatever a text edit can fix, "
            "rebuild and report how many findings remain and why."
        ),
    ),
    McpPrompt(
        name="review_changes",
        description="Описать несохранённые изменения и сохранить снимок / Describe changes and save a snapshot",
        arguments=(_PROJECT,),
        template_ru=(
            "Проект {project_id}. Посмотри vcs_status и vcs_diff, кратко опиши изменения по-русски одной строкой "
            "и предложи сохранить снимок с этим описанием (vcs_save_snapshot). Без моего согласия снимок не "
            "сохраняй."
        ),
        template_en=(
            "Project {project_id}. Look at vcs_status and vcs_diff, describe the changes in one line and offer to "
            "save a snapshot with that message (vcs_save_snapshot). Do not save it without my consent."
        ),
    ),
)

PROMPTS_BY_NAME: Mapping[str, McpPrompt] = {p.name: p for p in MCP_PROMPTS}


def get_prompt(name: str) -> McpPrompt:
    prompt = PROMPTS_BY_NAME.get(name)
    if prompt is None:
        raise McpError(McpErrorCode.not_found)
    return prompt
