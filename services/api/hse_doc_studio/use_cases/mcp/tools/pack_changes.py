"""`pack_changes`: панель «Изменения» и главная кнопка Студии шаблонов одним вызовом (pack-studio-mcp.md, P4).

Читает то же, что интерфейс: карточку пространства, дерево, git, линтер изменённых мест (не больше трёх), заметки
открытой версии и проверки хостинга открытого запроса. Статус и следующий шаг считает `core/pack_studio/
changes_status.py` (повтор `deriveChangesStatus` и `resolveNextStep`), подпись кнопки и подсказка словами
интерфейса (`pack_plain`). Только чтение.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import yaml

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.pack_studio.changes_status import (
    ChangesRaw,
    ChangesStatus,
    LintSummary,
    NextStep,
    derive_status,
    lint_targets,
    resolve_next_step,
)
from hse_doc_studio.core.pack_studio.entities import PackTree
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.core.pack_studio.git_flow import CiReport
from hse_doc_studio.core.pack_studio.paths import VERSION_MANIFEST, VersionRef, version_ref_of
from hse_doc_studio.use_cases.mcp.tools._base import optional_text, uuid_arg
from hse_doc_studio.use_cases.mcp.tools.pack_plain import next_step_hint, next_step_label, say
from hse_doc_studio.use_cases.mcp.tools.pack_view import FORMAT_PROP, layout_arg, layout_result
from hse_doc_studio.use_cases.mcp.tools.packs import (
    _VERSION,
    _WORKSPACE_ID,
    PackTool,
    _schema,
    accepted_fields,
    version_arg,
)
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.git import PackGitService
from hse_doc_studio.use_cases.pack_studio.insight import PackInsightService
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

# Какой тул делает следующий шаг: агенту не нужно угадывать.
STEP_TOOLS: Final[Mapping[str, tuple[str, ...]]] = {
    "connecting": ("pack_list_workspaces",),
    "checkAccess": ("pack_workspace_refresh",),
    "folder": (),
    "makeCopy": ("pack_new_version",),
    "toDraft": ("pack_changes",),
    "fixErrors": ("pack_lint", "pack_git_checks"),
    "describe": ("pack_version_notes",),
    "submit": ("pack_release", "pack_propose"),
    "request": ("pack_git_checks",),
    "updateRequest": ("pack_propose",),
    "startNew": ("pack_git_start_over",),
}
_MAX_FILES: Final = 50


def _versions(tree: PackTree) -> list[tuple[VersionRef, bool]]:
    found: list[tuple[VersionRef, bool]] = []
    for pack in tree.packs:
        for template in pack.templates:
            for version in template.versions:
                ref = version_ref_of(version.path)
                if ref is not None:
                    found.append((VersionRef(ref.pack, ref.template, ref.version), version.released))
    return found


def _number(ref: VersionRef) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in ref.version.split("."))


def pick_open(tree: PackTree, changed: list[str]) -> VersionRef | None:
    """Открытая версия без `version`: самая новая изменённая (черновики раньше), иначе самый новый черновик."""
    versions = _versions(tree)
    released = {ref.dir.casefold(): rel for ref, rel in versions}
    touched: dict[str, VersionRef] = {}
    for path in changed:
        ref = version_ref_of(path)
        if ref is not None:
            touched[ref.dir.casefold()] = VersionRef(ref.pack, ref.template, ref.version)
    pool = list(touched.values()) or [ref for ref, rel in versions if not rel] or [ref for ref, _ in versions]
    if not pool:
        return None
    pool.sort(key=_number, reverse=True)
    pool.sort(key=lambda ref: released.get(ref.dir.casefold(), False))
    return pool[0]


def _notes(text: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    block = data.get("changes") if isinstance(data, Mapping) else None

    def items(lang: str) -> tuple[str, ...]:
        raw = block.get(lang) if isinstance(block, Mapping) else None
        return tuple(str(i) for i in raw if isinstance(i, str) and i.strip()) if isinstance(raw, list) else ()

    return items("ru"), items("en")


def _step_view(step: NextStep | None) -> dict[str, Any] | None:
    if step is None:
        return None
    params: dict[str, object] = {}
    if step.count is not None:
        params["count"] = step.count
    if step.version is not None:
        params["version"] = step.version.version
    if step.label is not None:
        params["label"] = step.label
    if step.checks is not None:
        params["checks"] = step.checks.value
    if step.progress is not None:
        params["done"], params["total"] = step.progress
    return {
        "kind": step.kind,
        "label": next_step_label(step.kind, params),
        "hint": next_step_hint(step.kind),
        "tools": list(STEP_TOOLS.get(step.kind, ())),
        **({"version": step.version.dir} if step.version is not None else {}),
    }


def _state_mark(released: bool, accepted: bool) -> str:
    """Пометка версии в первой строке: выпущена или принята; у черновика пусто."""
    if released:
        return " (выпущена)" if current_interface_language().value == "ru" else " (released)"
    return f" ({say('state.accepted')})" if accepted else ""


def _text(
    ref: VersionRef | None, status: ChangesStatus, step: dict[str, Any] | None, files: list[str], *, accepted: bool
) -> str:
    ru = current_interface_language().value == "ru"
    lines = [
        ("Версия: " if ru else "Version: ") + (ref.dir if ref else "-") + _state_mark(status.released, accepted),
        (
            f"Изменено файлов: {status.changed_files}, в этой версии: {status.changed_in_version}"
            if ru
            else f"Files changed: {status.changed_files}, in this version: {status.changed_in_version}"
        ),
    ]
    if status.changed_elsewhere is not None:
        lines.append(
            ("Правки и в другой версии: " if ru else "Edits in another version: ") + status.changed_elsewhere.dir
        )
    lines.append(say("issues.summary", {"errors": status.errors, "warnings": status.warnings}))
    if status.notes_needed:
        lines.append("Нужны заметки «что изменилось»." if ru else "Notes on what changed are needed.")
    request = status.request
    if request.kind != "none":
        lines.append(("Запрос " if ru else "Request ") + f"{request.label}: {request.kind}")
    if status.behind:
        lines.append(
            f"Основная ветка ушла вперёд на {status.behind}" if ru else f"The main branch is {status.behind} ahead"
        )
    if step is not None:
        lines.append(
            ("Следующий шаг: " if ru else "Next step: ") + f"{step['label']} ({', '.join(step['tools']) or '-'})"
        )
        if step.get("hint"):
            lines.append(f"  {step['hint']}")
    lines += [f"  {f}" for f in files[:20]]
    return "\n".join(lines)


class PackChangesTool(PackTool):
    spec = ToolSpec(
        name="pack_changes",
        description=(
            "Студия шаблонов: что изменено и что делать дальше, как панель «Изменения» и главная кнопка интерфейса. "
            "Изменённые файлы и версии, ошибки и замечания проверки изменённых мест, нужны ли заметки, запрос на "
            "слияние и его проверки, отставание от основной ветки и next_step: подпись кнопки, подсказка и тулы, "
            "которые делают шаг. version: открытая версия (по умолчанию самая новая изменённая). accepted: запрос с "
            "этой версией принят, а пространство не обновляли (pack_workspace_refresh). Только чтение."
        ),
        parameters=_schema(
            {"workspace_id": _WORKSPACE_ID, "version": _VERSION, "format": FORMAT_PROP},
            ("workspace_id",),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:  # noqa: C901, PLR0912 — свод из пяти ответов
        workspace_id = uuid_arg(args, "workspace_id")
        ws = (await (await self._deps.get(PackWorkspaceService)).get(actor, workspace_id)).workspace
        files = await self._deps.get(PackFilesService)
        ready = ws.state.value == "ready"
        tree = (await files.tree(actor, workspace_id)).tree if ready else PackTree(packs=(), files=())
        changed: list[tuple[str, str]] = []
        git_ready = True
        git_view = None
        ci: CiReport | None = None
        if ready and ws.kind.value == "git":
            git = await self._deps.get(PackGitService)
            try:
                git_view = await git.view(actor, workspace_id)
                changed = [(c.path, c.status.value) for c in git_view.status.changed]
                if ws.pr_number is not None:
                    ci = await git.checks(actor, workspace_id)
            except (PackStudioError, GitSyncError):
                git_ready = git_view is not None
        open_ref = version_arg(args) if optional_text(args, "version") else pick_open(tree, [p for p, _ in changed])
        released_dirs = frozenset(ref.dir for ref, rel in _versions(tree) if rel)
        open_released = open_ref is not None and open_ref.dir in released_dirs
        lint: list[LintSummary] = []
        notes = None
        if git_view is not None and open_ref is not None:
            insight = await self._deps.get(PackInsightService)
            for target in lint_targets(changed, open_ref):
                try:
                    report = await insight.lint(actor, workspace_id, target)
                except PackStudioError:
                    continue
                lint.append(
                    LintSummary(
                        report.target, report.released, tuple((f.severity.value, f.message) for f in report.findings)
                    )
                )
            try:
                found = await files.read(actor, workspace_id, f"{open_ref.dir}/{VERSION_MANIFEST}")
                notes = _notes(found.content.decode("utf-8", errors="replace"))
            except PackStudioError:
                notes = None
        raw = ChangesRaw(
            workspace_kind=ws.kind.value,
            workspace_state=ws.state.value,
            open=open_ref or VersionRef("", "", ""),
            open_released=open_released,
            released_versions=released_dirs,
            git_ready=git_ready,
            changed=tuple(changed),
            lint=tuple(lint),
            notes=notes,
            provider=git_view.provider.value if git_view is not None else None,
            pr_number=ws.pr_number,
            pr_url=ws.pr_url,
            pushed_sha=ws.pushed_sha,
            head_sha=git_view.status.head_sha if git_view is not None else None,
            dirty=git_view.status.dirty if git_view is not None else False,
            ci_state=ci.state.value if ci is not None else None,
            ci_pr_state=ci.pr_state.value if ci is not None and ci.pr_state is not None else None,
            ci_checks=tuple(c.state.value for c in ci.checks) if ci is not None else (),
            behind=git_view.status.behind if git_view is not None else 0,
        )
        status = derive_status(raw)
        accepted = (
            open_ref is not None and not open_released and ci is not None and open_ref.dir in ci.accepted_versions
        )
        step = _step_view(resolve_next_step(status))
        request = status.request
        listed = [f"{s[:1].upper()} {p}" for p, s in changed[:_MAX_FILES]]
        data = {
            "workspace_id": str(workspace_id),
            "version": open_ref.dir if open_ref else None,
            "connection": status.connection.value,
            "workspace_kind": status.workspace_kind,
            "load": status.load,
            "released": status.released,
            **accepted_fields(accepted),
            "changed_files": status.changed_files,
            "changed_in_version": status.changed_in_version,
            "changed_elsewhere": status.changed_elsewhere.dir if status.changed_elsewhere else None,
            "errors": status.errors,
            "warnings": status.warnings,
            "notes_needed": status.notes_needed,
            "request": {
                "kind": request.kind,
                "number": request.number,
                "label": request.label,
                "url": request.url,
                "checks": request.checks.value,
                "progress": list(request.progress) if request.progress else None,
                "new_edits": request.new_edits,
            },
            "behind": status.behind,
            "checked": [r.target for r in lint],
            "files": listed,
            "next_step": step,
        }
        text = _text(open_ref, status, step, listed, accepted=accepted)
        return layout_result(layout_arg(args), text, data, truncated=len(changed) > _MAX_FILES)
