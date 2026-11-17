"""Git Студии шаблонов по шагам через MCP: ветки, коммит, diff, проверки, «обновить из базы», «начать заново».

Вместе с `pack_git_status` и `pack_propose` это весь поток «Предложить изменения» (template-studio.md, 4.3): ветка,
правки, коммит, проверки, diff, предложение. Тулы зовут `PackGitService`, как маршруты `/pack-studio/.../git*`: те же
замки пространства (`workspace_busy`), те же отказы. Коммит идёт от профиля человека (имя и почта профиля, не из
аргументов), токены доступа в ответы не попадают: push и выборка идут доступом пространства на стороне Студии.
`pack_git_start_over` стирает правки и забывает ветку и PR: без `confirm: true` только описывает последствия.
"""

from __future__ import annotations

from typing import Any, Final

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.pack_studio.entities import DiagnosticSeverity
from hse_doc_studio.core.pack_studio.git_flow import changed_versions
from hse_doc_studio.use_cases.mcp.tools._base import bool_arg, int_arg, jsonable, optional_text, uuid_arg
from hse_doc_studio.use_cases.mcp.tools.pack_view import (
    CONFIRM_PROP,
    FORMAT_PROP,
    clip_text,
    confirmed,
    layout_arg,
    layout_result,
)
from hse_doc_studio.use_cases.mcp.tools.packs import _WORKSPACE_ID, PackTool, _git, _schema
from hse_doc_studio.use_cases.pack_studio.git import GitView, PackGitService
from hse_doc_studio.use_cases.pack_studio.insight import PackInsightService

_DIFF_CHARS: Final = 20_000
_DIFF_MAX: Final = 120_000
_MAX_CHECKED_VERSIONS: Final = 10
_MAX_FINDINGS: Final = 50


def _git_text(view: GitView, head: str) -> str:
    st = view.status
    ws = view.workspace
    lines = [
        head,
        (
            f"Ветка: {st.branch or 'нет (дерево на вершине базы)'}; база: {ws.base_branch}; "
            f"впереди базы: {st.ahead}, позади: {st.behind}"
        ),
        f"Несохранённых правок: {len(st.uncommitted)}; отличий от базы: {len(st.changed)}",
    ]
    lines += [f"  {c.status.value[:1].upper()} {c.path}" for c in st.uncommitted[:30]]
    if ws.pr_url:
        lines.append(f"PR: {ws.pr_url}")
    elif view.compare_url:
        lines.append(f"Открыть PR: {view.compare_url}")
    return "\n".join(lines)


class PackGitBranchesTool(PackTool):
    spec = ToolSpec(
        name="pack_git_branches",
        description=(
            "Студия шаблонов: ветки пространства над git: текущая рабочая, базовая, локальные и отправленные на "
            "сервер (если сервер не ответил, server_unavailable). Имя для pack_git_branch берите отсюда."
        ),
        parameters=_schema({"workspace_id": _WORKSPACE_ID, "format": FORMAT_PROP}, ("workspace_id",)),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        found = await (await self._deps.get(PackGitService)).branches(actor, uuid_arg(args, "workspace_id"))
        data = jsonable(found)
        text = "\n".join(
            [
                f"Текущая: {found.current or 'нет'}; базовая: {found.base}",
                "Локальные: " + (", ".join(found.local) or "нет"),
                "На сервере: "
                + (", ".join(found.server) or "нет")
                + (" (сервер не ответил)" if found.server_unavailable else ""),
            ]
        )
        return layout_result(layout_arg(args), text, data)


class PackGitBranchTool(PackTool):
    spec = ToolSpec(
        name="pack_git_branch",
        description=(
            "Студия шаблонов: создать рабочую ветку или перейти на прежнюю (локальную или с сервера). Без name "
            "ветку называет Студия (pack-studio/<автор>/<версия>-<дата>), правки остаются на диске. С name: новая "
            "ветка от текущей вершины с правками, либо переход на существующую: дерево должно быть чистым "
            "(workspace_dirty: сначала pack_git_commit). Базовая ветка рабочей быть не может. Пример: "
            '{"workspace_id": "<uuid>", "name": "feature/new-points"}.'
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "name": {"type": "string", "description": "Имя ветки; пусто: имя даст Студия"},
                "format": FORMAT_PROP,
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        view = await (await self._deps.get(PackGitService)).switch(
            actor, uuid_arg(args, "workspace_id"), optional_text(args, "name")
        )
        return layout_result(layout_arg(args), _git_text(view, "Ветка выбрана."), _git(view))


class PackGitCommitTool(PackTool):
    spec = ToolSpec(
        name="pack_git_commit",
        description=(
            "Студия шаблонов: «Сохранить версию»: коммит несохранённых правок в рабочую ветку (без ветки она "
            "создаётся). Автор коммита: профиль человека. Без message Студия составит сообщение по соглашению "
            "(feat или fix по классу версии). Нет правок: committed false. Не отправляет ничего на сервер: "
            "для этого pack_propose."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "message": {"type": "string", "description": "Сообщение коммита (до 2000 знаков)"},
                "format": FORMAT_PROP,
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        done = await (await self._deps.get(PackGitService)).commit(
            actor, uuid_arg(args, "workspace_id"), optional_text(args, "message")
        )
        head = (
            f"Коммит {done.sha[:10]} создан."
            if done.committed and done.sha
            else "Нечего сохранять: несохранённых правок нет."
        )
        data = {"committed": done.committed, "sha": done.sha, "git": _git(done.git)}
        return layout_result(layout_arg(args), _git_text(done.git, head), data)


class PackGitDiffTool(PackTool):
    spec = ToolSpec(
        name="pack_git_diff",
        description=(
            "Студия шаблонов: единый diff от базовой ветки: коммиты рабочей ветки и правки на диске, то, что "
            "уйдёт в предложение. Перед pack_propose покажите его человеку. files_only: true только список "
            "файлов. max_chars обрезает текст (по умолчанию 20000)."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "files_only": {"type": "boolean", "default": False},
                "max_chars": {"type": "integer", "default": _DIFF_CHARS},
                "format": FORMAT_PROP,
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        git = await self._deps.get(PackGitService)
        view = await git.view(actor, workspace_id)
        files = [f"{c.status.value[:1].upper()} {c.path}" for c in view.status.changed]
        files_only = bool_arg(args, "files_only", False)
        body, cut = "", False
        if not files_only:
            raw, server_cut = await git.diff(actor, workspace_id)
            body, cut = clip_text(raw, int_arg(args, "max_chars", _DIFF_CHARS, lo=1_000, hi=_DIFF_MAX))
            cut = cut or server_cut
        text = f"Изменено файлов: {len(files)}\n" + "\n".join(files[:100])
        if body:
            text += "\n\n" + body
        elif not files_only:
            text += "\n(отличий от базы нет)"
        data: dict[str, Any] = {"files": files, "changed_total": len(files), "diff": body, "truncated": cut}
        return layout_result(layout_arg(args), text, data, truncated=cut)


class PackGitChecksTool(PackTool):
    spec = ToolSpec(
        name="pack_git_checks",
        description=(
            "Студия шаблонов: проверки перед предложением и после: pre_propose (то, что остановит pack_propose: "
            "ошибки pack_lint изменённых версий) и ci (статус проверок хостинга по отправленной вершине: none, "
            "pending, success, failure; available false: хостинг статус не отдаёт, смотрите web_url). Хостинг "
            "опрашивайте не чаще раза в 30 секунд, пока pending. ci: false пропускает запрос к хостингу."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "ci": {"type": "boolean", "default": True, "description": "Спросить статус у хостинга"},
                "format": FORMAT_PROP,
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        git = await self._deps.get(PackGitService)
        insight = await self._deps.get(PackInsightService)
        view = await git.view(actor, workspace_id)
        findings: list[dict[str, object]] = []
        errors = warnings = 0
        refs = changed_versions(view.status.changed)[:_MAX_CHECKED_VERSIONS]
        for ref in refs:
            report = await insight.lint(actor, workspace_id, ref.dir)
            for f in report.findings:
                if f.severity is DiagnosticSeverity.error:
                    errors += 1
                else:
                    warnings += 1
                if len(findings) < _MAX_FINDINGS:
                    findings.append(jsonable(f))  # type: ignore[arg-type]
        data: dict[str, Any] = {
            "pre_propose": {
                "versions": [r.dir for r in refs],
                "errors": errors,
                "warnings": warnings,
                "findings": findings,
                "will_block": errors > 0,
            }
        }
        lines = [
            f"Перед предложением: версий {len(refs)}, ошибок {errors}, предупреждений {warnings}"
            + (" (pack_propose остановится)" if errors else "")
        ]
        lines += [f"  {f.get('severity')}: {f.get('path') or f.get('file')}: {f.get('message')}" for f in findings[:20]]
        if bool_arg(args, "ci", True):
            ci = await git.checks(actor, workspace_id)
            data["ci"] = jsonable(ci)
            lines.append(f"CI хостинга: {ci.state.value}" + (f" ({ci.reason})" if ci.reason else ""))
            lines += [f"  {c.name}: {c.state.value}" for c in ci.checks[:20]]
        return layout_result(layout_arg(args), "\n".join(lines), data)


class PackGitMergeBaseTool(PackTool):
    spec = ToolSpec(
        name="pack_git_merge_base",
        description=(
            "Студия шаблонов: «Обновить из базы»: выборка базовой ветки и слияние её в рабочую. Дерево должно быть "
            "чистым (workspace_dirty: pack_git_commit). Конфликт отменяет слияние: merge_conflict со списком "
            "files, ничего не меняется."
        ),
        parameters=_schema({"workspace_id": _WORKSPACE_ID, "format": FORMAT_PROP}, ("workspace_id",)),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        view = await (await self._deps.get(PackGitService)).merge_base(actor, uuid_arg(args, "workspace_id"))
        return layout_result(layout_arg(args), _git_text(view, "База влита в рабочую ветку."), _git(view))


class PackGitStartOverTool(PackTool):
    spec = ToolSpec(
        name="pack_git_start_over",
        description=(
            "Студия шаблонов: «Начать заново от базовой ветки» (обычно после слияния PR): дерево встаёт на свежую "
            "вершину базы, рабочая ветка, PR и статус проверок забываются. ДЕСТРУКТИВНО: несохранённые правки "
            "пропадают (только с discard: true), коммиты ветки остаются в её истории на диске, но рабочей она "
            "больше не будет. Без confirm: true ничего не делает и описывает, что будет потеряно."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "confirm": CONFIRM_PROP,
                "discard": {
                    "type": "boolean",
                    "default": False,
                    "description": "Согласие потерять несохранённые правки (без него при правках workspace_dirty)",
                },
                "format": FORMAT_PROP,
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        git = await self._deps.get(PackGitService)
        discard = bool_arg(args, "discard", False)
        if not confirmed(args):
            view = await git.view(actor, workspace_id)
            st = view.status
            lost = [c.path for c in st.uncommitted]
            data: dict[str, Any] = {
                "confirm_required": True,
                "branch": st.branch,
                "pull_request": view.workspace.pr_url,
                "unsaved_files": lost[:100],
                "will_forget_branch": st.branch is not None,
                "hint": localized_error(
                    "Ничего не изменено. Покажите человеку, что будет потеряно, и вызовите с confirm: true"
                    + (" и discard: true" if lost else "")
                    + ".",
                    "Nothing was changed. Show the person what will be lost and call with confirm: true"
                    + (" and discard: true" if lost else "")
                    + ".",
                ),
            }
            text = (
                f"Начать заново сотрёт {len(lost)} несохранённых файлов и забудет ветку {st.branch or '(нет)'}"
                f"{' и PR' if view.workspace.pr_url else ''}.\n" + str(data["hint"])
            )
            return layout_result(layout_arg(args), text, data)
        view = await git.start_over(actor, workspace_id, discard=discard)
        return layout_result(layout_arg(args), _git_text(view, "Дерево на свежей базе, ветка забыта."), _git(view))


__all__ = [
    "PackGitBranchTool",
    "PackGitBranchesTool",
    "PackGitChecksTool",
    "PackGitCommitTool",
    "PackGitDiffTool",
    "PackGitMergeBaseTool",
    "PackGitStartOverTool",
]
