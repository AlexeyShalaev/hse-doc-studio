"""`pack_help`: каталог возможностей Студии шаблонов для агента.

Список всех тулов `pack_*` по задачам (с первой фразой их описаний, поэтому он не расходится с каталогом) и порядок
типового сценария «создать шаблон и ветку, исправить, проверить, предложить». Читает только каталог тулов, ничего не
вызывает.
"""

from __future__ import annotations

import re
from typing import Any, Final

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, optional_text
from hse_doc_studio.use_cases.mcp.tools.pack_view import FORMAT_PROP, layout_arg, layout_result
from hse_doc_studio.use_cases.mcp.tools.packs import PackTool, _schema

GROUPS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "workspaces": (
        "Пространства / Workspaces",
        (
            "pack_list_workspaces",
            "pack_list_credentials",
            "pack_workspace_create",
            "pack_workspace_refresh",
            "pack_workspace_delete",
            "pack_official",
            "pack_official_open",
            "pack_catalog",
        ),
    ),
    "read": (
        "Чтение / Reading",
        ("pack_tree", "pack_read", "pack_read_file", "pack_model", "pack_hints", "pack_doc_library", "pack_submission"),
    ),
    "edit": (
        "Правка / Editing",
        (
            "pack_create",
            "pack_new_template",
            "pack_scaffold_options",
            "pack_write_file",
            "pack_patch_yaml",
            "pack_move_file",
            "pack_delete_file",
            "pack_model_action",
            "pack_submission_edit",
            "pack_set_placement",
        ),
    ),
    "check": (
        "Проверка / Checking",
        ("pack_lint", "pack_classify", "pack_preview_build", "pack_preview_read"),
    ),
    "outcome": (
        "Результат и сценарии / Outcome and scenarios",
        (
            "pack_outcome_inputs",
            "pack_outcome",
            "pack_outcome_atlas",
            "pack_outcome_explain",
            "pack_outcome_matrix",
            "pack_outcome_compare",
            "pack_outcome_impact",
            "pack_scenario_list",
            "pack_scenario_write",
            "pack_scenario_delete",
            "pack_scenario_run",
        ),
    ),
    "version": ("Версии / Versions", ("pack_new_version", "pack_version_notes", "pack_release")),
    "git": (
        "Git и предложение / Git and proposal",
        (
            "pack_git_status",
            "pack_git_branches",
            "pack_git_branch",
            "pack_git_commit",
            "pack_git_diff",
            "pack_git_checks",
            "pack_git_merge_base",
            "pack_git_start_over",
            "pack_propose",
        ),
    ),
}

FLOW_RU: Final = (
    (
        "1. pack_list_workspaces: найдите пространство (или pack_workspace_create / pack_official_open; доступ git "
        "берётся из pack_list_credentials, токены через MCP не передаются)."
    ),
    "2. pack_git_branch: создайте рабочую ветку (name или без имени).",
    (
        "3. pack_create (новый пак) или pack_new_template (шаблон в паке); pack_scaffold_options покажет варианты. "
        "Выпущенную версию править нельзя: pack_new_version создаёт черновик."
    ),
    (
        "4. Правки: pack_patch_yaml (точечно по JSON Pointer, с if_match), pack_model_action, pack_submission_edit, "
        "pack_set_placement или pack_write_file (файл целиком, с if_match из pack_read_file)."
    ),
    "5. pack_lint: ошибки не дадут предложить изменения; pack_classify: класс версии.",
    (
        "6. pack_outcome_inputs и pack_outcome: что получится при вводных; pack_outcome_atlas и pack_outcome_explain: "
        "какие вводные что меняют и почему. pack_scenario_write фиксирует ожидания, pack_scenario_run проверяет их."
    ),
    "7. pack_preview_build: настоящая сборка PDF на раннере (по необходимости).",
    "8. pack_git_commit: сохранить версию; pack_git_diff и pack_outcome_impact: что изменится против базы.",
    "9. pack_git_checks: ошибки перед предложением; pack_git_merge_base: влить свежую базу.",
    (
        "10. pack_propose (опасный, выключен по умолчанию): сначала confirm false (сводка), затем confirm true. "
        "После слияния PR: pack_git_start_over."
    ),
)
FLOW_EN: Final = (
    (
        "1. pack_list_workspaces: find the workspace (or pack_workspace_create / pack_official_open; git access comes "
        "from pack_list_credentials, tokens are never passed through MCP)."
    ),
    "2. pack_git_branch: create a work branch (name or none).",
    (
        "3. pack_create (new pack) or pack_new_template (template in a pack); pack_scaffold_options lists options. A "
        "released version is immutable: pack_new_version creates a draft."
    ),
    (
        "4. Edits: pack_patch_yaml (targeted by JSON Pointer, with if_match), pack_model_action, pack_submission_edit, "
        "pack_set_placement or pack_write_file (whole file, with if_match from pack_read_file)."
    ),
    "5. pack_lint: errors block the proposal; pack_classify: the version class.",
    (
        "6. pack_outcome_inputs and pack_outcome: what results for given inputs; pack_outcome_atlas and "
        "pack_outcome_explain: which inputs change what and why. pack_scenario_write pins expectations, "
        "pack_scenario_run checks them."
    ),
    "7. pack_preview_build: a real PDF build on a runner (when needed).",
    "8. pack_git_commit: save; pack_git_diff and pack_outcome_impact: what changes against the base.",
    "9. pack_git_checks: errors before proposing; pack_git_merge_base: merge the fresh base.",
    (
        "10. pack_propose (dangerous, off by default): confirm false first (summary), then confirm true. After the PR "
        "is merged: pack_git_start_over."
    ),
)
_SENTENCE = re.compile(r"^(?:Студия шаблонов:\s*)?(.+?[.:;])(?:\s|$)", re.S)


def _summary(description: str) -> str:
    match = _SENTENCE.match(description)
    return (match.group(1) if match else description)[:160].rstrip(".:;")


class PackHelpTool(PackTool):
    spec = ToolSpec(
        name="pack_help",
        description=(
            "Студия шаблонов: каталог возможностей для агента: все инструменты pack_* по задачам (пространства, "
            "чтение, правка, проверка, результат и сценарии, версии, git и предложение) и порядок типового "
            "сценария «создать шаблон и ветку, исправить, проверить, предложить». topic: all (по умолчанию), "
            "flow (только порядок) или группа workspaces, read, edit, check, outcome, version, git. Начните с "
            "него, если не знаете, каким тулом сделать действие. Только чтение."
        ),
        parameters=_schema({"topic": {"type": "string", "default": "all"}, "format": FORMAT_PROP}),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:  # noqa: C901 — разделы справки
        from hse_doc_studio.use_cases.mcp.catalog import MCP_TOOL_CLASSES, RULES_BY_NAME  # noqa: PLC0415 — цикл импорта

        topic = optional_text(args, "topic") or "all"
        if topic not in {"all", "flow", *GROUPS}:
            raise ArgumentError(f"topic: all, flow, {', '.join(GROUPS)}")
        specs = {cls.spec.name: cls for cls in MCP_TOOL_CLASSES if cls.spec.name.startswith("pack_")}
        ru = current_interface_language().value == "ru"
        flow = FLOW_RU if ru else FLOW_EN
        data: dict[str, Any] = {"flow": list(flow), "groups": {}}
        lines: list[str] = []
        if topic != "flow":
            named = {name for _, (_, names) in GROUPS.items() for name in names}
            extra = sorted(set(specs) - named - {"pack_help"})
            for key, (title, names) in GROUPS.items():
                if topic not in {"all", key}:
                    continue
                label = title.split(" / ")[0 if ru else 1]
                entries = []
                lines.append(f"{label}:")
                for name in (*names, *(extra if key == "git" and topic in {"all", key} else ())):
                    cls = specs.get(name)
                    if cls is None:
                        continue
                    rule = RULES_BY_NAME.get(name)
                    mode = "write" if cls.kind is ToolKind.write else "exec" if cls.kind is ToolKind.exec_ else "read"
                    dangerous = bool(rule and rule.meta.dangerous)
                    entries.append(
                        {"name": name, "kind": mode, "dangerous": dangerous, "summary": _summary(cls.spec.description)}
                    )
                    lines.append(
                        f"  {name} [{mode}{', off by default' if dangerous else ''}]: {_summary(cls.spec.description)}"
                    )
                data["groups"][key] = entries
        if topic in {"all", "flow"}:
            lines.append("")
            lines.append("Типовой сценарий:" if ru else "Typical flow:")
            lines += [f"  {step}" for step in flow]
        if topic == "flow":
            data.pop("groups")
        return layout_result(layout_arg(args), "\n".join(lines).strip(), data)
