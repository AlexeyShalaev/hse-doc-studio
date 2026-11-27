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
            "pack_checks",
            "pack_set_placement",
        ),
    ),
    "check": (
        "Проверка / Checking",
        (
            "pack_lint",
            "pack_classify",
            "pack_preview_build",
            "pack_preview_read",
            "pack_signature_render",
            "pack_signature_check",
        ),
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
            "pack_outcome_lint",
            "pack_scenario_list",
            "pack_scenario_write",
            "pack_scenario_delete",
            "pack_scenario_run",
        ),
    ),
    "version": (
        "Версии / Versions",
        ("pack_new_version", "pack_version_number", "pack_version_notes", "pack_release"),
    ),
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
            "pack_changes",
            "pack_propose",
        ),
    ),
}

FLOW_RU: Final = (
    (
        "1. pack_list_workspaces: найдите пространство (или pack_workspace_create / pack_official_open; доступ git "
        "берётся из pack_list_credentials, токены через MCP не передаются)."
    ),
    (
        "2. pack_git_branch: создайте рабочую ветку (name или без имени). Следующую работу после слияния PR "
        "начинайте с from_base: true: новая ветка от свежей базовой, а не от текущей вершины."
    ),
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
        "какие вводные что меняют и почему. pack_scenario_write фиксирует ожидания, pack_scenario_run проверяет их; "
        "pack_outcome_lint ищет дефекты правил и показывает покрытие сценариями."
    ),
    (
        "7. pack_preview_build: настоящая сборка PDF на раннере. Места подписей: pack_signature_render (картинка "
        "страницы с рамками), pack_signature_check (проверка и suggested_ops), pack_set_placement с build_id, снова "
        "render и check."
    ),
    (
        "8. pack_changes: что изменено и следующий шаг (как кнопка «Изменения»); pack_git_commit: сохранить точку; "
        "pack_git_diff и pack_outcome_impact: что изменится против основной ветки."
    ),
    "9. pack_git_checks: ошибки перед предложением; pack_git_merge_base: влить свежую базу.",
    (
        "10. pack_propose (опасный, выключен по умолчанию): сначала confirm false (сводка), затем confirm true. "
        "После слияния PR: pack_git_branch с from_base: true (сразу новая ветка от свежей базы) или "
        "pack_git_start_over (дерево на базу без ветки)."
    ),
)
FLOW_EN: Final = (
    (
        "1. pack_list_workspaces: find the workspace (or pack_workspace_create / pack_official_open; git access comes "
        "from pack_list_credentials, tokens are never passed through MCP)."
    ),
    (
        "2. pack_git_branch: create a work branch (name or none). Start the next piece of work after a merged PR "
        "with from_base: true: a new branch from the fresh base branch, not from the current head."
    ),
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
        "pack_scenario_run checks them; "
        "pack_outcome_lint finds rule defects and shows the scenario coverage."
    ),
    (
        "7. pack_preview_build: a real PDF build on a runner. Signature places: pack_signature_render (the page with "
        "boxes), pack_signature_check (findings and suggested_ops), pack_set_placement with build_id, then render and "
        "check again."
    ),
    (
        "8. pack_changes: what changed and the next step (like the Changes button); pack_git_commit: save a point; "
        "pack_git_diff and pack_outcome_impact: what changes against the main branch."
    ),
    "9. pack_git_checks: errors before proposing; pack_git_merge_base: merge the fresh base.",
    (
        "10. pack_propose (dangerous, off by default): confirm false first (summary), then confirm true. After the PR "
        "is merged: pack_git_branch with from_base: true (a new branch from the fresh base right away) or "
        "pack_git_start_over (the tree on the base with no branch)."
    ),
)
TEAM_TITLE_RU: Final = "Командный проект: строка каждого автора"
TEAM_TITLE_EN: Final = "Team project: a line for every author"
_TEAM_EXAMPLE: Final = (
    "((* for a in project.authors *))",
    r"\hseSignAnchor[7cm]{author__{{ a.slug }}}\rule{7cm}{0.4pt} {{ a.name | texesc }}",
    r"\hseDateAnchor[8mm]{author__{{ a.slug }}}{day}\rule{8mm}{0.4pt}",
    "((* endfor *))",
)
TEAM_RU: Final = (
    TEAM_TITLE_RU,
    (
        "В команде слот per_author размножается по авторам (author--<слаг>), а общий документ (scope: shared) "
        "подписывают все авторы. Если шаблон ставит на строке каждого автора один и тот же якорь author, Студия видит "
        "один якорь и место из пака на общем документе не ставит: все авторы встали бы в одну рамку."
    ),
    (
        "Поставьте на строке автора якорь с его слагом: имя слота, два подчёркивания и {{ a.slug }} в цикле по "
        "авторам. Документ подключает common/anchors (\\input{../common/anchors})."
    ),
    *(f"    {line}" for line in _TEAM_EXAMPLE),
    (
        "- version.yaml не меняется: запись остаётся anchor: author (метка даты anchor: author.day), строку каждого "
        "автора Студия берёт сама."
    ),
    (
        "- Годится обёртка из signatures.anchor_macros (\\authorsignatureline[author__{{ a.slug }}]{7cm}) и свои "
        "макросы: цикл по авторам в common/ передаёт author__{{ a.slug }} аргументом, а \\hseSignAnchor{#2} стоит в "
        "макросе строки."
    ),
    "- Личные документы и solo: якорь остаётся author.",
    "- Двойное подчёркивание занято под этот разделитель; имя якоря целиком не длиннее 40 знаков.",
    (
        "Проверка: pack_lint (предупреждение про слот per_author на общем документе пропадает), pack_preview_build "
        "с combination {staffing: team2 или team3}, затем pack_signature_render и pack_signature_check: рамка на "
        "каждого автора (author--<слаг>). Запись в паке одна на всех: двигайте слот author, сдвинутся все."
    ),
)
TEAM_EN: Final = (
    TEAM_TITLE_EN,
    (
        "In a team the per_author slot is copied per author (author--<slug>), and a shared document (scope: shared) "
        "is signed by every author. If the template puts the same author anchor on each author's line, the Studio "
        "sees one anchor and does not set the pack place on the shared document: every author would land in one box."
    ),
    (
        "Put an anchor with the author's slug on his line: the slot name, two underscores and {{ a.slug }} in the loop "
        "over authors. The document includes common/anchors (\\input{../common/anchors})."
    ),
    *(f"    {line}" for line in _TEAM_EXAMPLE),
    (
        "- version.yaml stays as is: the entry keeps anchor: author (a date mark anchor: author.day), the Studio takes "
        "each author's line itself."
    ),
    (
        "- A wrapper from signatures.anchor_macros works (\\authorsignatureline[author__{{ a.slug }}]{7cm}), and so do "
        "your own macros: a loop over authors in common/ passes author__{{ a.slug }} as an argument and "
        "\\hseSignAnchor{#2} sits in the row macro."
    ),
    "- Personal documents and solo projects keep the author anchor.",
    "- The double underscore is reserved for this separator; the whole anchor name is at most 40 characters.",
    (
        "Check: pack_lint (the warning about a per_author slot on a shared document goes away), pack_preview_build "
        "with combination {staffing: team2 or team3}, then pack_signature_render and pack_signature_check: a box for "
        "every author (author--<slug>). The pack has one entry for all: move the author slot and every box moves."
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
            "flow (только порядок), группа workspaces, read, edit, check, outcome, version, git или раздел формата "
            "team (командный проект: строка и место подписи каждого автора, якорь author__<слаг>). Начните с "
            "него, если не знаете, каким тулом сделать действие. Только чтение."
        ),
        parameters=_schema({"topic": {"type": "string", "default": "all"}, "format": FORMAT_PROP}),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:  # noqa: C901 — разделы справки
        from hse_doc_studio.use_cases.mcp.catalog import MCP_TOOL_CLASSES, RULES_BY_NAME  # noqa: PLC0415 — цикл импорта

        topic = optional_text(args, "topic") or "all"
        if topic not in {"all", "flow", "team", *GROUPS}:
            raise ArgumentError(f"topic: all, flow, team, {', '.join(GROUPS)}")
        specs = {cls.spec.name: cls for cls in MCP_TOOL_CLASSES if cls.spec.name.startswith("pack_")}
        ru = current_interface_language().value == "ru"
        team = TEAM_RU if ru else TEAM_EN
        if topic == "team":
            return layout_result(layout_arg(args), "\n".join(team), {"team": list(team)})
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
        if topic == "all":
            data["topics"] = {"team": team[0]}
            lines.append("")
            lines.append(f"{'Формат пака' if ru else 'Pack format'}: topic: team ({team[0]})")
        if topic == "flow":
            data.pop("groups")
        return layout_result(layout_arg(args), "\n".join(lines).strip(), data)
