"""Студия шаблонов через MCP: тулы `pack_*` (docs/design/template-studio.md, раздел 11; срезы T16 и T15).

Тулы зовут те же сценарии, что маршруты `/api/v1/pack-studio`, с теми же проверками:

- раздел включён, есть право «Автор шаблонов», у токена область `packs` (`PackStudioAccess.require`, как гард
  маршрутов); без права тулы скрыты из `tools/list` (`PackStudioToolGate`);
- пространства только свои (сценарий ищет пространство владельца), запись только в невыпущенные версии
  (`version_released`), `releases.yaml` меняет только мастер версии (`releases_read_only`);
- операции git и мастера версии под замком пространства (`workspace_busy`).

Отказ сценария это ответ с ошибкой `{code, detail, ...}`: код из `contracts/pack-studio/error_codes.json` или
`contracts/git-sync/error_codes.json` и поля по коду (`stale_file` с ETag, `lint_failed` с находками, `fork_required`
с `can_create`), чтобы агент мог поправить и повторить. Токены доступа git в ответы не попадают: `pack_propose`
пользуется доступом пространства на стороне Студии.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Final
from uuid import UUID

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat, TemplateUpdateClass, ToolKind
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.mcp.entities import McpToolGroup, McpToolMeta
from hse_doc_studio.core.pack_studio.entities import DiagnosticSeverity, PackWorkspace
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.core.pack_studio.paths import TEMPLATES_DIR, VERSIONS_DIR, VersionRef, version_ref_of
from hse_doc_studio.core.pack_studio.places import MarkBox, PlaceBox, PlaceOp, PlaceOpKind
from hse_doc_studio.core.pack_studio.preview import PreviewBuild
from hse_doc_studio.core.pack_studio.protocols import IPdfTextReader
from hse_doc_studio.core.pack_studio.scaffold import (
    Maintainer,
    NewPack,
    NewTemplate,
    Scaffold,
    ScaffoldKind,
    ScaffoldResult,
    ScaffoldSource,
    SourceOrigin,
)
from hse_doc_studio.core.pack_studio.versions import LANGS, VersionNotesInput, VersionState
from hse_doc_studio.use_cases.mcp.tools._base import (
    MCP_MAX_WAIT_S,
    ArgumentError,
    McpTool,
    bool_arg,
    int_arg,
    json_result,
    jsonable,
    optional_text,
    text_arg,
    uuid_arg,
    wait_arg,
)
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.git import ForkChoice, GitView, PackGitService, ProposeInput
from hse_doc_studio.use_cases.pack_studio.insight import PackInsightService
from hse_doc_studio.use_cases.pack_studio.official import OfficialPacks
from hse_doc_studio.use_cases.pack_studio.places import PackPlacesService
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, PreviewOptions, StartPreviewInput
from hse_doc_studio.use_cases.pack_studio.scaffold import CreatePackInput, CreateTemplateInput, PackScaffoldService
from hse_doc_studio.use_cases.pack_studio.versions import CreateVersionInput, PackVersionService, ReleaseInput
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService, WorkspaceView

# Сколько ждать сборку предпросмотра в одном вызове: меньше таймаута запроса у клиентов MCP (60 с в SDK).
# Ожидание сборки в одном вызове: не дольше MCP_MAX_WAIT_S, дальше повторный вызов с build_id.
PREVIEW_WAIT_S: Final = 45
_POLL_S = 0.5
# Сколько символов файла, журнала и PDF уходит в ответ по умолчанию и не больше.
_READ_CHARS: Final = 60_000
_LOG_TAIL: Final = 4_000
_PDF_CHARS: Final = 8_000
_MAX_LISTED: Final = 200
_CTX_CHARS: Final = 4_000

_WORKSPACE_ID = {"type": "string", "description": "Id рабочего пространства (UUID) из pack_list_workspaces"}
_VERSION = {
    "type": "string",
    "description": "Версия шаблона: «<пак>/<шаблон>/<версия>» (имена папок, как в pack_read), например "
    "«hse-cs-sse/coursework/2026.1.7»",
}
_PATH = {
    "type": "string",
    "description": "Путь от папки паков пространства, например «hse-cs-sse/templates/coursework/versions/2026.1.7/"
    "version.yaml»",
}
_LOCALIZED_LIST = {
    "type": "object",
    "properties": {
        "ru": {"type": "array", "items": {"type": "string"}},
        "en": {"type": "array", "items": {"type": "string"}},
    },
    "description": "Пункты парами: списки ru и en одной длины",
}


def _schema(properties: Mapping[str, Any], required: Sequence[str] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties), "required": list(required)}


def _clip(value: object) -> object:
    if isinstance(value, str) and len(value) > _CTX_CHARS:
        return value[:_CTX_CHARS] + "…"
    if isinstance(value, list):
        return [_clip(v) for v in value[:50]]
    return value


_HINTS: Final[dict[str, tuple[str, str]]] = {
    "version_released": (
        "Выпущенная версия неизменяема: создайте черновик тулом pack_new_version и правьте его.",
        "A released version is immutable: create a draft with pack_new_version and edit that.",
    ),
    "releases_read_only": (
        "Реестр выпусков ведёт pack_release: правьте через мастер версии, а не файлом.",
        "pack_release maintains the release registry: use the version wizard, not a file edit.",
    ),
    "stale_file": (
        "Файл изменился после чтения: перечитайте (pack_read_file) и повторите правку с новым etag.",
        "The file changed after you read it: reread it (pack_read_file) and repeat the edit with the new etag.",
    ),
    "workspace_dirty": (
        "Есть несохранённые правки: сохраните их pack_git_commit и повторите.",
        "There are uncommitted edits: save them with pack_git_commit and retry.",
    ),
    "refresh_dirty": (
        (
            "База выбрана, но дерево не сдвинуто: есть несохранённые правки. Сохраните их (pack_git_commit) и влейте "
            "базу (pack_git_merge_base) или отбросьте (pack_git_start_over с discard), затем pack_workspace_refresh."
        ),
        (
            "The base was fetched but the tree did not move: there are uncommitted edits. Save them (pack_git_commit) "
            "and merge the base (pack_git_merge_base), or discard them (pack_git_start_over with discard), then call "
            "pack_workspace_refresh."
        ),
    ),
    "workspace_busy": (
        "С пространством идёт другая операция (клон, выборка, git): повторите через несколько секунд.",
        "Another operation (clone, fetch, git) is running on the workspace: retry in a few seconds.",
    ),
    "workspace_not_ready": (
        (
            "Пространство ещё скачивается или с ошибкой: состояние покажет pack_list_workspaces, при ошибке "
            "pack_workspace_refresh."
        ),
        (
            "The workspace is still cloning or failed: pack_list_workspaces shows the state; on failure use "
            "pack_workspace_refresh."
        ),
    ),
    "not_a_git_workspace": (
        "У пространства-папки нет git: ветки, коммиты и предложение доступны у пространства над репозиторием.",
        "A folder workspace has no git: branches, commits and proposals need a repository workspace.",
    ),
    "merge_conflict": (
        (
            "База конфликтует с вашими правками: слияние отменено. Решите конфликт в файлах из files (pack_read_file, "
            "pack_write_file), сохраните и повторите."
        ),
        "The base conflicts with your edits: the merge was cancelled. Resolve the files in files, commit and retry.",
    ),
    "lint_failed": (
        "Проверки нашли ошибки: поправьте их (pack_lint покажет файл и строку) и повторите.",
        "Checks found errors: fix them (pack_lint shows the file and line) and retry.",
    ),
    "branch_name_invalid": (
        "Допустимое имя ветки: латиница, цифры, «-», «_», «/»; базовую ветку рабочей делать нельзя.",
        "Use Latin letters, digits, '-', '_' and '/'; the base branch cannot be the work branch.",
    ),
    "branch_exists": (
        (
            "Ветка с таким именем уже есть (pack_git_branches). Для новой ветки от базы дайте свободное имя или "
            "уберите name: имя даст Студия. Перейти на существующую: pack_git_branch без from_base."
        ),
        (
            "This branch already exists (pack_git_branches). For a new branch from the base pass a free name or "
            "drop name: the Studio names it. To switch to the existing one call pack_git_branch without from_base."
        ),
    ),
    "credentials_missing": (
        (
            "Такого сохранённого доступа нет: добавьте доступ git в интерфейсе (Настройки, Git) и возьмите его id из "
            "pack_list_credentials. Токены через MCP не передаются."
        ),
        (
            "No such saved access: add git access in the interface (Settings, Git) and take its id from "
            "pack_list_credentials. Tokens are never passed through MCP."
        ),
    ),
    "service_access_missing": (
        "Подключённого репозитория нет: добавьте доступ git в интерфейсе и укажите credential_id.",
        "The repository is not connected: add git access in the interface and pass credential_id.",
    ),
    "yaml_patch_conflict": (
        (
            "Правка не применилась (поле op в ответе указывает номер): сверьте путь с содержимым pack_read_file; "
            "файл не изменён."
        ),
        (
            "The edit was not applied (op is the operation number): check the path against pack_read_file; the file is "
            "unchanged."
        ),
    ),
    "model_invalid": (
        "Правка сломала бы манифест (reason): файл не изменён. Поправьте значение и повторите.",
        "The edit would break the manifest (reason): the file is unchanged. Fix the value and retry.",
    ),
    "scenario_taken": (
        "Сценарий с таким id уже есть: для правки передайте if_match (etag из pack_scenario_list).",
        "A scenario with this id exists: pass if_match (etag from pack_scenario_list) to edit it.",
    ),
    "pack_scope_required": (
        "Токену нужна область packs: выпустите токен с областями mcp и packs.",
        "The token needs the packs scope: issue a token with the mcp and packs scopes.",
    ),
    "pack_studio_forbidden": (
        "Нужен доступ к Студии шаблонов: его выдаёт админ установки.",
        "Access to Template Studio is required: the installation admin grants it.",
    ),
}


def default_hint(exc: PackStudioError | GitSyncError) -> str | None:
    """Что делать по коду отказа: следующий шаг для агента (если у тула нет своей подсказки)."""
    pair = _HINTS.get(exc.code.value)
    return localized_error(*pair) if pair is not None else None


def refusal(exc: PackStudioError | GitSyncError, *, hint: str | None = None) -> ToolResult:
    """Отказ сценария: код, текст на языке интерфейса и поля по коду (длинные строки обрезаны); `hint` что делать."""
    hint = hint or default_hint(exc)
    if isinstance(exc, GitSyncError):
        body: dict[str, object] = {"code": exc.code.value, "detail": exc.detail}
    else:
        body = {"code": exc.code.value, "detail": exc.detail}
        body.update({str(k): _clip(jsonable(v)) for k, v in exc.ctx.items()})
    if hint:
        body["hint"] = hint
    return ToolResult.error(json.dumps(body, ensure_ascii=False, indent=1))


class PackStudioToolGate:
    """Тулы Студии шаблонов видит только тот, кому открыт раздел (`IMcpToolGate`); остальные группы как есть."""

    def __init__(self, access: PackStudioAccess) -> None:
        self._access = access

    async def allows(self, actor: Actor, meta: McpToolMeta) -> bool:
        if meta.group is not McpToolGroup.packs:
            return True
        return await self._access.allowed(actor)


class PackTool(McpTool):
    """Тул Студии шаблонов: вне проекта, проверка раздела как у маршрутов, отказ сценария ответом с кодом."""

    requires_project: ClassVar[bool] = False

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        actor = require_actor()
        try:
            await (await self._deps.get(PackStudioAccess)).require(actor)
            return await self.run(actor, args)
        except (PackStudioError, GitSyncError) as exc:
            return refusal(exc)

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        raise NotImplementedError


def version_arg(args: Mapping[str, object], key: str = "version") -> VersionRef:
    """`<пак>/<шаблон>/<версия>` или путь внутри каталога версии от папки паков."""
    raw = text_arg(args, key).strip("/")
    parts = raw.split("/")
    path = f"{parts[0]}/{TEMPLATES_DIR}/{parts[1]}/{VERSIONS_DIR}/{parts[2]}" if len(parts) == 3 else raw  # noqa: PLR2004
    ref = version_ref_of(path)
    if ref is None:
        raise ArgumentError(
            localized_error(
                f"{key}: ожидается «<пак>/<шаблон>/<версия>», получено {raw!r}",
                f"{key}: «<pack>/<template>/<version>» is expected, got {raw!r}",
            )
        )
    return VersionRef(ref.pack, ref.template, ref.version)


def _workspace(view: WorkspaceView, official: OfficialPacks | None) -> dict[str, object]:
    ws = view.workspace
    return {
        "id": ws.id,
        "label": ws.label,
        "kind": ws.kind,
        "state": ws.state,
        "busy": view.busy,
        "source": ws.remote_url or view.folder_display,
        "packs_path": ws.packs_path,
        "base_branch": ws.base_branch,
        "work_branch": ws.work_branch,
        "pull_request": ws.pr_url,
        "ci_status": ws.ci_status,
        "fork": ws.fork_url,
        "official": official is not None and official.is_official(ws),
        "error": None if ws.error is None else _workspace_error(ws.error.code, ws.error.detail),
    }


def _workspace_error(code: str, detail: str) -> dict[str, object]:
    """Ошибка карточки пространства: код, текст и, если он есть для кода, что делать тулами MCP."""
    error: dict[str, object] = {"code": code, "detail": detail}
    pair = _HINTS.get(code)
    if pair is not None:
        error["hint"] = localized_error(*pair)
    return error


def _git(view: GitView) -> dict[str, object]:
    status = view.status
    ws: PackWorkspace = view.workspace
    return {
        "branch": status.branch,
        "base_branch": ws.base_branch,
        "head_sha": status.head_sha,
        "ahead": status.ahead,
        "behind": status.behind,
        "uncommitted": [jsonable(c) for c in status.uncommitted[:_MAX_LISTED]],
        "changed": [jsonable(c) for c in status.changed[:_MAX_LISTED]],
        "changed_total": len(status.changed),
        "pull_request": ws.pr_url,
        "compare_url": view.compare_url,
        "fork": ws.fork_url,
        "ci_status": ws.ci_status,
        "license_accepted_at": ws.license_accepted_at,
    }


# ── пространства и чтение ───────────────────────────────────────────────────


class PackListWorkspacesTool(PackTool):
    spec = ToolSpec(
        name="pack_list_workspaces",
        description=(
            "Студия шаблонов: ваши рабочие пространства паков (git-репозиторий паков или папка на диске). Id "
            "пространства нужен остальным тулам pack_*. Пространство в состоянии cloning ещё скачивается."
        ),
        parameters=_schema({}),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        views = await (await self._deps.get(PackWorkspaceService)).list(actor)
        official = await self._deps.get(OfficialPacks)
        return json_result({"workspaces": [_workspace(v, official) for v in views]})


class PackReadTool(PackTool):
    spec = ToolSpec(
        name="pack_read",
        description=(
            "Студия шаблонов: без version дерево пространства (паки, шаблоны, версии со статусом; released: "
            "выпущена и только для чтения). С version разобранная модель версии: документы, поля анкеты, слоты "
            "подписей, точки сдачи, анкеты, языки, файлы версии и preview: что можно собрать в pack_preview_build "
            "(документы, переключатели combination с допустимыми значениями, наборы данных, умолчания). Пример: "
            '{"workspace_id": "<uuid>", "version": "hse-cs-sse/coursework/2026.1.7"}.'
        ),
        parameters=_schema({"workspace_id": _WORKSPACE_ID, "version": _VERSION}, ("workspace_id",)),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        files = await self._deps.get(PackFilesService)
        view = await files.tree(actor, workspace_id)
        if not optional_text(args, "version"):
            return json_result({"packs": view.tree.packs, "truncated": view.tree.truncated})
        ref = version_arg(args)
        previews = await self._deps.get(PackPreviewService)
        desc = await previews.describe(actor, workspace_id, ref.pack, ref.template, ref.version)
        prefix = f"{ref.dir}/".casefold()
        listed = [f for f in view.tree.files if not f.is_dir and f.path.casefold().startswith(prefix)]
        released = next(
            (
                v.released
                for p in view.tree.packs
                for t in p.templates
                for v in t.versions
                if v.path.casefold() == ref.dir.casefold()
            ),
            False,
        )
        model = _model(desc.version)
        options = await previews.options(actor, workspace_id, ref.pack, ref.template, ref.version)
        model.update(
            {
                "path": ref.dir,
                "released": released,
                "examples": [e.id for e in desc.examples],
                "preview": _preview_options(options),
                "files": [{"path": f.path, "size": f.size, "read_only": f.read_only} for f in listed[:_MAX_LISTED]],
                "files_total": len(listed),
            }
        )
        return json_result(model, truncated=len(listed) > _MAX_LISTED)


def _preview_options(options: PreviewOptions) -> dict[str, Any]:
    """Что можно собрать (как `GET .../preview`): документы, переключатели, наборы данных и умолчания."""
    return {
        "documents": [d.id for d in options.documents],
        "switches": [
            {"id": s.id, "values": list(s.values), "default": s.default, "label": s.label} for s in options.switches
        ],
        "examples": [{"id": e.id, "source": e.source, "label": e.label, "error": e.error} for e in options.examples],
        "default_example": options.default_example,
        "combination": dict(options.combination),
        "languages": {doc: list(langs) for doc, langs in options.languages.items()},
    }


def _model(version: TemplateVersion) -> dict[str, Any]:
    signatures = version.signatures_config
    return {
        "version": version.version,
        "status": version.status,
        "summary": version.summary,
        "langs": version.langs,
        "supported_staffing": version.supported_staffing,
        "documents": [
            {
                "id": d.id,
                "name": d.name,
                "source_file": d.source_file,
                "output_file": d.output_file,
                "scope": d.scope,
                "required": d.required,
                "supported_langs": d.supported_langs,
                "supported_kinds": d.supported_kinds,
            }
            for d in version.documents
        ],
        "meta_groups": [{"id": g.id, "label": g.label} for g in version.meta_groups],
        "meta_fields": [
            {
                "key": key,
                "type": f.type,
                "label": f.label,
                "group": f.group,
                "required_at": f.required_at,
                "default": f.default,
                "auto": f.auto,
                "options": f.options,
            }
            for key, f in version.meta_fields.items()
        ],
        "signature_slots": [
            {
                "id": s.id,
                "label": s.label,
                "applies_to": s.applies_to,
                "required": s.required,
                "per_author": s.per_author,
                "placements": [doc for doc, _ in s.placements],
                "default_dates": [doc for doc, _ in s.default_dates],
            }
            for s in signatures.slots
        ],
        "signing_route": signatures.route,
        "submission_profiles": [
            {
                "id": p.id,
                "name": p.name,
                "items": [{"doc_id": i.doc_id, "signatures": i.signatures} for i in p.items],
                "signing_route": p.signing_route,
                "deadline_hint": p.deadline_hint,
            }
            for p in version.pack_submission.profiles
        ],
        "forms": [{"id": f.id, "title": f.title} for f in version.forms],
        "dynamic_includes": [jsonable(d) for d in version.dynamic_includes],
        "changes": version.changes,
    }


class PackReadFileTool(PackTool):
    spec = ToolSpec(
        name="pack_read_file",
        description=(
            "Студия шаблонов: текст файла пака и его etag (для pack_write_file с if_match). read_only называет, "
            "почему файл менять нельзя: version_released (выпущенная версия) или releases_read_only (реестр "
            "выпусков ведёт мастер версии)."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "path": _PATH,
                "max_chars": {"type": "integer", "default": _READ_CHARS, "description": "Сколько символов вернуть"},
            },
            ("workspace_id", "path"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        found = await (await self._deps.get(PackFilesService)).read(
            actor, uuid_arg(args, "workspace_id"), text_arg(args, "path")
        )
        try:
            text = found.content.decode("utf-8")
        except UnicodeDecodeError:
            return ToolResult.error(
                localized_error(
                    f"{found.path}: двоичный файл, его нельзя прочитать как текст",
                    f"{found.path}: a binary file, it cannot be read as text",
                )
            )
        limit = int_arg(args, "max_chars", _READ_CHARS, lo=1_000, hi=_READ_CHARS * 4)
        truncated = len(text) > limit
        return json_result(
            {
                "path": found.path,
                "etag": found.etag,
                "read_only": found.read_only,
                "size": len(found.content),
                "truncated": truncated,
                "content": text[:limit],
            },
            truncated=truncated,
        )


class PackWriteFileTool(PackTool):
    spec = ToolSpec(
        name="pack_write_file",
        description=(
            "Студия шаблонов: записать файл пака целиком (создать или заменить). Только в невыпущенные версии: "
            "выпущенная отвечает version_released, новую версию создаёт pack_new_version. if_match (etag из "
            "pack_read_file) защищает от чужой правки: устаревший отвечает stale_file с текущим etag. После записи "
            "проверьте версию тулом pack_lint."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "path": _PATH,
                "content": {"type": "string", "description": "Новый текст файла (UTF-8)"},
                "if_match": {"type": "string", "description": "Etag версии файла, на которую опирается правка"},
            },
            ("workspace_id", "path", "content"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        content = args.get("content")
        if not isinstance(content, str):
            raise ArgumentError(localized_error("укажите параметр content", "specify the content parameter"))
        written = await (await self._deps.get(PackFilesService)).write(
            actor,
            uuid_arg(args, "workspace_id"),
            text_arg(args, "path"),
            content.encode("utf-8"),
            optional_text(args, "if_match"),
        )
        return json_result({"path": written.path, "etag": written.etag, "size": written.size})


# ── проверки и класс ────────────────────────────────────────────────────────


class PackLintTool(PackTool):
    spec = ToolSpec(
        name="pack_lint",
        description=(
            "Студия шаблонов: проверка пака. Путь внутри версии проверяет всю версию (pack_lint и схемы "
            "манифестов), pack.yaml, template.yaml и releases.yaml проверяются схемой. Находки с файлом и строкой; "
            "ошибки не дадут предложить изменения (pack_propose)."
        ),
        parameters=_schema({"workspace_id": _WORKSPACE_ID, "path": _PATH}, ("workspace_id", "path")),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        report = await (await self._deps.get(PackInsightService)).lint(
            actor, uuid_arg(args, "workspace_id"), text_arg(args, "path")
        )
        findings = report.findings
        return json_result(
            {
                "scope": report.scope,
                "target": report.target,
                "released": report.released,
                "errors": sum(1 for f in findings if f.severity is DiagnosticSeverity.error),
                "warnings": sum(1 for f in findings if f.severity is DiagnosticSeverity.warning),
                "findings": list(findings[:_MAX_LISTED]),
            },
            truncated=len(findings) > _MAX_LISTED,
        )


def _state(state: VersionState) -> dict[str, object]:
    return {
        "version": state.ref.dir,
        "status": state.status,
        "released": state.released,
        "modified": state.modified,
        "registered": state.registered,
        "release_outdated": state.release_outdated,
        "is_default": state.is_default,
        "base": state.base,
        "minimum": state.minimum,
        "suggested": state.suggested,
        "by_number": state.by_number,
        "declared": state.declared,
        "number_ok": state.number_ok,
        "headline": state.headline,
        "reasons": [
            {
                "code": r.code,
                "path": r.path,
                "change": r.change,
                "minimum": r.minimum,
                "suggested": r.suggested,
                "hard": r.hard,
                "message": r.message,
            }
            for r in state.reasons
        ],
        "numbers": state.numbers,
        "note": state.note,
        "changes": state.changes,
        "breaking_changes": state.breaking_changes,
        "draft_changes": state.draft_changes,
        "draft_breaking_changes": state.draft_breaking,
        "move_to": state.move_to,
        "error": state.error,
    }


class PackClassifyTool(PackTool):
    spec = ToolSpec(
        name="pack_classify",
        description=(
            "Студия шаблонов: класс черновика версии по изменениям (patch, minor, major) с причинами относительно "
            "предыдущей выпущенной, номер не мягче минимума (number_ok), номера по классам, заметки changes и их "
            "черновик из отчёта. У выпущенной версии только признак правки мимо Студии (modified, move_to)."
        ),
        parameters=_schema({"workspace_id": _WORKSPACE_ID, "version": _VERSION}, ("workspace_id", "version")),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        state = await (await self._deps.get(PackVersionService)).state(
            actor, uuid_arg(args, "workspace_id"), ref.pack, ref.template, ref.version
        )
        return json_result(_state(state))


# ── предпросмотр ────────────────────────────────────────────────────────────


def _build(build: PreviewBuild) -> dict[str, object]:
    return {
        "build_id": build.id,
        "version": f"{build.pack}/{build.template}/{build.version}",
        "document": build.document,
        "example": build.example,
        "combination": build.combination,
        "variant": build.variant,
        "file_name": build.file_name,
        "scenario": build.scenario,
        "status": build.status,
        "cached": build.cached,
        "pages": build.pages,
        "error": None if build.error is None else jsonable(build.error),
    }


def _combination(args: Mapping[str, object]) -> dict[str, str] | None:
    raw = args.get("combination")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ArgumentError(
            localized_error("combination: ожидается объект {переключатель: значение}", "combination: an object")
        )
    return {str(k): str(v) for k, v in raw.items()}


def _strings(args: Mapping[str, object], key: str) -> list[str]:
    raw = args.get(key)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    raise ArgumentError(localized_error(f"{key}: ожидается список строк", f"{key}: a list of strings is expected"))


class PackPreviewBuildTool(PackTool):
    spec = ToolSpec(
        name="pack_preview_build",
        description=(
            "Студия шаблонов: собрать документы версии на тестовых данных в песочнице раннера и дождаться итога до "
            f"wait_s секунд (не больше {MCP_MAX_WAIT_S}: больший урезается, иначе клиент MCP оборвёт вызов по "
            "таймауту). Долгую сборку начните без ожидания (wait_s: 0) или с коротким и вызывайте снова с build_id, "
            "пока она не закончится. Без documents собирается первый документ. example: набор данных (по "
            "умолчанию первый: файл examples/*.yaml или auto:normal; ещё auto:long и auto:empty), combination: "
            'переключатели {"lang": "en", "staffing": "team2", "supervisor": "company", "meta.<поле>": "..."}. '
            "variant: вариант документа (у запроса с одним документом, например beamer у презентации), scenario: "
            "id сценария пака (вводные и набор данных берутся из него, combination ложится поверх). Варианты, "
            "документы и наборы "
            "видны в pack_read с version (блок preview). С build_id тул только ждёт уже начатую сборку, с build_id "
            "и cancel: true останавливает её. "
            "Текст PDF и журнал сборки читает pack_preview_read."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "documents": {"type": "array", "items": {"type": "string"}, "description": "Id документов"},
                "example": {"type": "string", "description": "Набор данных"},
                "combination": {"type": "object", "description": "Переключатели комбинации"},
                "variant": {"type": "string", "description": "Вариант документа (один документ в запросе)"},
                "scenario": {"type": "string", "description": "Id сценария пака"},
                "build_id": {"type": "string", "description": "Ждать уже начатую сборку"},
                "cancel": {"type": "boolean", "default": False, "description": "С build_id: остановить сборку"},
                "wait_s": {
                    "type": "integer",
                    "default": PREVIEW_WAIT_S,
                    "description": (
                        f"Сколько секунд ждать итога в этом вызове (0..{MCP_MAX_WAIT_S}, больше урезается); "
                        "дольше: повторный вызов с build_id"
                    ),
                },
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.exec_

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        wait_s = wait_arg(args, PREVIEW_WAIT_S)
        previews = await self._deps.get(PackPreviewService)
        if bool_arg(args, "cancel", False):
            stopped = await previews.cancel(actor, workspace_id, uuid_arg(args, "build_id"))
            return json_result({"builds": [_build(stopped)]})
        if optional_text(args, "build_id"):
            builds = [await previews.get(actor, workspace_id, uuid_arg(args, "build_id"))]
        else:
            ref = version_arg(args)
            documents = _strings(args, "documents")
            if not documents:
                desc = await previews.describe(actor, workspace_id, ref.pack, ref.template, ref.version)
                documents = [d.id for d in desc.version.documents[:1]]
            builds = await previews.start(
                actor,
                workspace_id,
                ref.pack,
                ref.template,
                ref.version,
                StartPreviewInput(
                    documents=documents,
                    example=optional_text(args, "example"),
                    combination=_combination(args),
                    variant=optional_text(args, "variant"),
                    scenario=optional_text(args, "scenario"),
                ),
            )
        deadline = time.monotonic() + wait_s
        while any(not b.status.is_terminal for b in builds) and time.monotonic() < deadline:
            await asyncio.sleep(_POLL_S)
            builds = [await previews.get(actor, workspace_id, b.id) for b in builds]
        views = [_build(b) for b in builds]
        running = any(not b.status.is_terminal for b in builds)
        hint = (
            localized_error(
                "Сборка ещё идёт: вызовите pack_preview_build с build_id, чтобы дождаться итога.",
                "The build is still running: call pack_preview_build with build_id to wait for the result.",
            )
            if running
            else localized_error(
                "Текст PDF и журнал сборки: pack_preview_read с build_id.",
                "The PDF text and the build log: pack_preview_read with build_id.",
            )
        )
        result = json_result({"builds": views, "hint": hint})
        if not running and all(b.status.value == "failed" for b in builds):
            return ToolResult.error(result.text)
        return result


class PackPreviewReadTool(PackTool):
    spec = ToolSpec(
        name="pack_preview_read",
        description=(
            "Студия шаблонов: что получилось у сборки предпросмотра. what: pdf (текст страниц, pages как "
            "«1-3» или «1,4»), log (хвост журнала: [render] предупреждения рендера и вывод latexmk)."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "build_id": {"type": "string", "description": "Id сборки из pack_preview_build"},
                "what": {"type": "string", "enum": ["pdf", "log"], "default": "pdf"},
                "pages": {"type": "string", "description": "Страницы PDF: «1-3», «5» или «1,4,7»"},
                "max_chars": {"type": "integer", "default": _PDF_CHARS},
            },
            ("workspace_id", "build_id"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        build_id = uuid_arg(args, "build_id")
        previews = await self._deps.get(PackPreviewService)
        limit = int_arg(args, "max_chars", _PDF_CHARS, lo=500, hi=_READ_CHARS)
        if (optional_text(args, "what") or "pdf") == "log":
            log = await previews.log(actor, workspace_id, build_id)
            return ToolResult.ok(log[-limit:] or "-", truncated=len(log) > limit)
        path = await previews.pdf(actor, workspace_id, build_id)
        data = await asyncio.to_thread(path.read_bytes)
        reader = await self._deps.get(IPdfTextReader)  # type: ignore[type-abstract]  # порт из контейнера
        text, total = await asyncio.to_thread(
            lambda: reader.read(data, pages=_pages(optional_text(args, "pages")), max_chars=limit)
        )
        header = localized_error(f"{total} стр.", f"{total} p.")
        return ToolResult.ok(f"{header}\n\n{text}", truncated="[..." in text)


def _pages(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    pages: list[int] = []
    for part in raw.replace(" ", "").split(","):
        if "-" in part:
            lo, _, hi = part.partition("-")
            if lo.isdigit() and hi.isdigit():
                pages.extend(range(int(lo), min(int(hi), int(lo) + 200) + 1))
        elif part.isdigit():
            pages.append(int(part))
    return pages or None


# ── места подписей ──────────────────────────────────────────────────────────

_BOX = {
    "type": "object",
    "properties": {
        "page": {"type": "integer"},
        "x_mm": {"type": "number"},
        "y_mm": {"type": "number"},
        "width_mm": {"type": "number"},
    },
    "description": "Рамка подписи, мм от левого верхнего угла страницы",
}
_MARK = {
    "type": "object",
    "properties": {
        **_BOX["properties"],  # type: ignore[dict-item]
        "height_mm": {"type": "number"},
        "format": {"type": "string", "description": "day, month_word, month_number, year, date_numeric и др."},
        "align": {"type": "string", "enum": ["left", "center", "right"]},
    },
    "description": "Метка даты",
}


def _number(raw: Mapping[str, object], key: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ArgumentError(localized_error(f"{key}: ожидается число", f"{key}: a number is expected"))
    return float(value)


def _place_box(raw: object) -> PlaceBox | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error("box: ожидается объект", "box: an object is expected"))
    return PlaceBox(int(_number(raw, "page")), _number(raw, "x_mm"), _number(raw, "y_mm"), _number(raw, "width_mm"))


def _mark_box(raw: object) -> MarkBox | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error("mark: ожидается объект", "mark: an object is expected"))
    try:
        fmt = DateMarkFormat(str(raw.get("format")))
        align = DateMarkAlign(str(raw.get("align") or DateMarkAlign.centered.value))
    except ValueError as exc:
        raise ArgumentError(str(exc)) from None
    return MarkBox(
        int(_number(raw, "page")),
        _number(raw, "x_mm"),
        _number(raw, "y_mm"),
        _number(raw, "width_mm"),
        _number(raw, "height_mm"),
        fmt,
        align,
    )


def _place_op(raw: object) -> PlaceOp:
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error("ops: ожидается список объектов", "ops: a list of objects is expected"))
    try:
        kind = PlaceOpKind(str(raw.get("op")))
    except ValueError:
        names = ", ".join(k.value for k in PlaceOpKind)
        raise ArgumentError(localized_error(f"op: одно из {names}", f"op: one of {names}")) from None
    index = raw.get("index")
    doc = raw.get("doc")
    anchor = raw.get("anchor")
    return PlaceOp(
        op=kind,
        slot=text_arg(raw, "slot"),
        doc=str(doc) if isinstance(doc, str) and doc else None,
        box=_place_box(raw.get("box")),
        index=index if isinstance(index, int) and not isinstance(index, bool) else None,
        mark=_mark_box(raw.get("mark")),
        anchor=str(anchor) if isinstance(anchor, str) and anchor else None,
    )


class PackSetPlacementTool(PackTool):
    spec = ToolSpec(
        name="pack_set_placement",
        description=(
            "Студия шаблонов: места подписей и метки даты слота в version.yaml (то же, что визуальный редактор "
            "мест). ops до 50, весь набор или ничего: set_place (box; без doc это общее место слота), remove_place, "
            "make_default, bind_anchor и unbind_anchor (нужна сборка build_id с якорями), add_date (mark в мм или "
            "anchor «слот.часть»), set_date и remove_date по index. Координаты округляются до 1 мм. Пример: "
            '{"op": "set_place", "slot": "supervisor", "doc": "report", '
            '"box": {"page": 1, "x_mm": 80, "y_mm": 139, "width_mm": 40}}. Без ops отдаёт текущий каталог мест.'
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": [k.value for k in PlaceOpKind]},
                            "slot": {"type": "string"},
                            "doc": {"type": "string"},
                            "box": _BOX,
                            "index": {"type": "integer"},
                            "mark": _MARK,
                            "anchor": {"type": "string"},
                        },
                        "required": ["op", "slot"],
                    },
                },
                "build_id": {"type": "string", "description": "Сборка предпросмотра документа: рамки по её якорям"},
                "if_match": {"type": "string", "description": "Etag version.yaml"},
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        workspace_id = uuid_arg(args, "workspace_id")
        build_id = uuid_arg(args, "build_id") if optional_text(args, "build_id") else None
        places = await self._deps.get(PackPlacesService)
        raw_ops = args.get("ops")
        if raw_ops is None or raw_ops == []:
            view = await places.get(actor, workspace_id, ref.pack, ref.template, ref.version, build_id)
        else:
            if not isinstance(raw_ops, list):
                raise ArgumentError(localized_error("ops: ожидается список", "ops: a list is expected"))
            ops = [_place_op(op) for op in raw_ops]
            view = await places.edit(
                actor, workspace_id, ref.pack, ref.template, ref.version, build_id, ops, optional_text(args, "if_match")
            )
        return json_result({"path": view.path, "etag": view.etag, "read_only": view.read_only, "places": view.places})


# ── мастер версии ───────────────────────────────────────────────────────────


def _update_class(args: Mapping[str, object], key: str) -> TemplateUpdateClass | None:
    raw = optional_text(args, key)
    if raw is None:
        return None
    try:
        return TemplateUpdateClass(raw)
    except ValueError:
        raise ArgumentError(
            localized_error(f"{key}: patch, minor или major", f"{key}: patch, minor or major")
        ) from None


class PackNewVersionTool(PackTool):
    spec = ToolSpec(
        name="pack_new_version",
        description=(
            "Студия шаблонов: шаг 1 мастера «Новая версия». Каталог базы (по умолчанию последняя выпущенная) "
            "копируется в черновик beta с пустыми заметками; номер явно (version) или по классу update_class "
            "(patch по умолчанию). Занятый номер отвечает version_taken с suggested. dry_run: true ничего не "
            "создаёт и показывает варианты: версии шаблона, базу по умолчанию и номера по классам. Пример: "
            '{"workspace_id": "<uuid>", "pack": "hse-cs-sse", "template": "coursework", "update_class": "patch"}.'
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "pack": {"type": "string", "description": "Папка пака"},
                "template": {"type": "string", "description": "Папка шаблона"},
                "base": {"type": "string", "description": "Версия-база копии"},
                "version": {"type": "string", "description": "Номер новой версии, ГОД.MINOR.PATCH"},
                "update_class": {"type": "string", "enum": ["patch", "minor", "major"]},
                "dry_run": {"type": "boolean", "default": False, "description": "true: только варианты, без записи"},
            },
            ("workspace_id", "pack", "template"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        service = await self._deps.get(PackVersionService)
        if bool_arg(args, "dry_run", False):
            options = await service.options(
                actor, uuid_arg(args, "workspace_id"), text_arg(args, "pack"), text_arg(args, "template")
            )
            return json_result(
                {
                    "template": f"{options.template.pack}/{options.template.template}",
                    "versions": [jsonable(v) for v in options.versions],
                    "default_base": options.default_base,
                    "default_version": options.default_version,
                    "numbers": {str(getattr(k, "value", k)): v for k, v in options.numbers.items()},
                }
            )
        created = await service.create(
            actor,
            uuid_arg(args, "workspace_id"),
            text_arg(args, "pack"),
            text_arg(args, "template"),
            CreateVersionInput(
                base=optional_text(args, "base"),
                version=optional_text(args, "version"),
                update_class=_update_class(args, "update_class"),
            ),
        )
        return json_result(
            {
                "version": created.ref.dir,
                "base": created.base,
                "update_class": created.update_class,
                "warnings": created.warnings,
                "hint": localized_error(
                    "Правьте файлы черновика (pack_write_file), класс показывает pack_classify, заметки "
                    "pack_version_notes, выпуск pack_release.",
                    "Edit the draft files (pack_write_file); pack_classify shows the class, pack_version_notes "
                    "writes the notes, pack_release releases.",
                ),
            }
        )


def _localized_list(raw: object, key: str) -> dict[str, tuple[str, ...]] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error(f"{key}: ожидается {{ru: [...], en: [...]}}", f"{key}: {{ru, en}}"))
    result: dict[str, tuple[str, ...]] = {}
    for lang in LANGS:
        items = raw.get(lang) or []
        if not isinstance(items, list):
            raise ArgumentError(localized_error(f"{key}.{lang}: ожидается список", f"{key}.{lang}: a list"))
        result[lang] = tuple(str(item) for item in items)
    return result


class PackVersionNotesTool(PackTool):
    spec = ToolSpec(
        name="pack_version_notes",
        description=(
            "Студия шаблонов: заметки черновика версии: changes и breaking_changes (пункты парами ru и en, длины "
            "списков равны) и note (объяснение класса для мягких правил, release.note). Переданное заменяет "
            "прежнее, остальное не меняется. Черновик заметок даёт pack_classify (draft_changes)."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "changes": _LOCALIZED_LIST,
                "breaking_changes": _LOCALIZED_LIST,
                "note": {"type": "string", "description": "Объяснение класса; пустая строка убирает"},
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        note = args.get("note")
        notes = VersionNotesInput(
            changes=_localized_list(args.get("changes"), "changes"),
            breaking_changes=_localized_list(args.get("breaking_changes"), "breaking_changes"),
            note=note if isinstance(note, str) else None,
        )
        state = await (await self._deps.get(PackVersionService)).save_notes(
            actor, uuid_arg(args, "workspace_id"), ref.pack, ref.template, ref.version, notes
        )
        return json_result(_state(state))


class PackReleaseTool(PackTool):
    spec = ToolSpec(
        name="pack_release",
        description=(
            "Студия шаблонов: шаг «Выпустить» мастера версии: status: stable, released_at сегодня, release.kind, "
            "по set_default версия становится default_version шаблона, запись в releases.yaml после проверки "
            "линтером (lint_failed с находками). У git это правки рабочей ветки: выпущенной версия станет после "
            "слияния PR (pack_propose). Номер, уже выпущенный в базе, отвечает version_taken."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "kind": {"type": "string", "enum": ["patch", "minor", "major"], "description": "Класс строже номера"},
                "set_default": {"type": "boolean", "default": False},
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        released = await (await self._deps.get(PackVersionService)).release(
            actor,
            uuid_arg(args, "workspace_id"),
            ref.pack,
            ref.template,
            ref.version,
            ReleaseInput(kind=_update_class(args, "kind"), set_default=bool_arg(args, "set_default", False)),
        )
        return json_result(
            {
                "version": released.ref.dir,
                "digest": released.digest,
                "kind": released.kind,
                "previous": released.previous,
                "replaced": released.replaced,
                "default_set": released.default_set,
                "edited": released.edited,
                "warnings": released.warnings,
            }
        )


# ── git ─────────────────────────────────────────────────────────────────────


class PackGitStatusTool(PackTool):
    spec = ToolSpec(
        name="pack_git_status",
        description=(
            "Студия шаблонов: git рабочего пространства над репозиторием: рабочая ветка, правки после коммита, "
            "отличия от базы, ahead и behind, PR или ссылка compare. С checks: true ещё статус проверок хостинга "
            "(CI) по отправленной вершине."
        ),
        parameters=_schema(
            {"workspace_id": _WORKSPACE_ID, "checks": {"type": "boolean", "default": False}}, ("workspace_id",)
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        git = await self._deps.get(PackGitService)
        view = _git(await git.view(actor, workspace_id))
        if bool_arg(args, "checks", False):
            view["checks"] = jsonable(await git.checks(actor, workspace_id))
        return json_result(view)


class PackProposeTool(PackTool):
    spec = ToolSpec(
        name="pack_propose",
        description=(
            "Студия шаблонов: «Предложить изменения»: коммит несохранённого, проверка изменённых шаблонов "
            "(lint_failed с находками), push рабочей ветки и PR (GitHub) или MR (GitLab) в базовую ветку доступом "
            "пространства. Внешнее действие: сначала вызовите с confirm: false и покажите человеку сводку (ветка, "
            "файлы, куда уйдёт), затем с confirm: true. Нет права push: fork_required (can_create: форк можно "
            "создать), повтор с fork_url или create_fork: true. Официальные паки: первое предложение требует "
            "accept_license: true (вклад публичен, под лицензией репозитория)."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "confirm": {"type": "boolean", "default": False, "description": "true: выполнить; false: сводка"},
                "title": {"type": "string", "description": "Заголовок PR; по умолчанию составит Студия"},
                "description": {"type": "string", "description": "Описание PR сверх сводки Студии"},
                "message": {"type": "string", "description": "Сообщение коммита несохранённых правок"},
                "fork_url": {"type": "string", "description": "Адрес своего форка на том же хосте"},
                "create_fork": {"type": "boolean", "default": False},
                "accept_license": {"type": "boolean", "default": False},
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.exec_

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        git = await self._deps.get(PackGitService)
        if not bool_arg(args, "confirm", False):
            return await self._summary(actor, workspace_id, git)
        fork_url = optional_text(args, "fork_url")
        create = bool_arg(args, "create_fork", False)
        proposed = await git.propose(
            actor,
            workspace_id,
            ProposeInput(
                title=optional_text(args, "title"),
                description=optional_text(args, "description"),
                message=optional_text(args, "message"),
                fork=ForkChoice(url=fork_url, create=create) if fork_url or create else None,
                accept_license=bool_arg(args, "accept_license", False),
            ),
        )
        report = proposed.report
        return json_result(
            {
                "pushed_sha": proposed.pushed_sha,
                "pushed_to": proposed.pushed_to,
                "pull_request": jsonable(proposed.pull_request),
                "compare_url": proposed.compare_url,
                "pr_error": None
                if proposed.pr_error is None
                else {"code": proposed.pr_error.code.value, "detail": proposed.pr_error.detail},
                "checks": {"errors": report.errors, "warnings": report.warnings},
                "git": _git(proposed.git),
            }
        )

    async def _summary(self, actor: Actor, workspace_id: UUID, git: PackGitService) -> ToolResult:
        view = await git.view(actor, workspace_id)
        ws = view.workspace
        official = (await self._deps.get(OfficialPacks)).is_official(ws)
        summary = _git(view)
        summary.update(
            {
                "confirm_required": True,
                "repository": ws.remote_url,
                "official": official,
                "license_consent_needed": official and ws.license_accepted_at is None,
                "nothing_to_propose": not view.status.changed,
                "hint": localized_error(
                    "Ничего не отправлено. Покажите человеку ветку и файлы; чтобы отправить и открыть PR, вызовите "
                    "pack_propose с confirm: true.",
                    "Nothing was sent. Show the branch and files to the person; to push and open a PR, call "
                    "pack_propose with confirm: true.",
                ),
            }
        )
        return json_result(summary)


# ── пак и шаблон с нуля (срез T15) ──────────────────────────────────────────

_LOCALIZED_TEXT = {
    "type": "object",
    "properties": {"ru": {"type": "string"}, "en": {"type": "string"}},
    "description": "Текст ru и en; пустой перевод берёт текст другого языка",
}
_SCAFFOLD_SOURCE = {
    "type": "object",
    "properties": {
        "origin": {"type": "string", "enum": ["workspace", "catalog"]},
        "pack": {"type": "string"},
        "template": {"type": "string"},
        "version": {"type": "string"},
    },
    "required": ["origin", "pack", "template", "version"],
    "description": "Что копировать (из pack_scaffold_options); без него заготовка «Минимальный»",
}


def _text_pair(args: Mapping[str, object], key: str) -> dict[str, str] | None:
    raw = args.get(key)
    if raw is None:
        return None
    if isinstance(raw, str):
        return {"ru": raw, "en": ""}
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error(f"{key}: ожидается {{ru, en}}", f"{key}: {{ru, en}} is expected"))
    return {lang: str(raw.get(lang) or "") for lang in LANGS}


def _scaffold(args: Mapping[str, object]) -> Scaffold:
    raw = args.get("copy_from")
    if raw is None:
        return Scaffold()
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error("copy_from: ожидается объект", "copy_from: an object is expected"))
    try:
        origin = SourceOrigin(str(raw.get("origin") or "workspace"))
    except ValueError:
        raise ArgumentError(localized_error("copy_from.origin: workspace или catalog", "copy_from.origin")) from None
    return Scaffold(
        kind=ScaffoldKind.copy,
        source=ScaffoldSource(origin, text_arg(raw, "pack"), text_arg(raw, "template"), text_arg(raw, "version")),
    )


def _new_template(args: Mapping[str, object], prefix: str = "template") -> NewTemplate:
    return NewTemplate(
        id=text_arg(args, f"{prefix}_id"),
        name=_text_pair(args, f"{prefix}_name") or {},
        short_name=_text_pair(args, f"{prefix}_short_name"),
    )


def _created(result: ScaffoldResult) -> dict[str, object]:
    return {
        "version": result.ref.dir,
        "pack_created": result.pack_created,
        "manifests": result.manifests,
        "main_file": result.main_file,
        "files": result.files,
        "source": result.source,
        "hint": localized_error(
            "Проверьте версию (pack_lint), соберите документ (pack_preview_build) и правьте файлы черновика.",
            "Check the version (pack_lint), build a document (pack_preview_build) and edit the draft files.",
        ),
    }


class PackScaffoldOptionsTool(PackTool):
    spec = ToolSpec(
        name="pack_scaffold_options",
        description=(
            "Студия шаблонов: что нужно для pack_create и pack_new_template: версии, которые можно скопировать "
            "(origin workspace: паки пространства, catalog: паки каталога этой Студии), занятые id паков, "
            "сопровождающий и лицензия по умолчанию, номер первой версии."
        ),
        parameters=_schema({"workspace_id": _WORKSPACE_ID}, ("workspace_id",)),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        options = await (await self._deps.get(PackScaffoldService)).options(actor, uuid_arg(args, "workspace_id"))
        return json_result(options)


class PackCreateTool(PackTool):
    spec = ToolSpec(
        name="pack_create",
        description=(
            "Студия шаблонов: новый пак с первым шаблоном и черновой версией beta. Без copy_from заготовка "
            "«Минимальный»: «Отчёт» по ГОСТ 7.32 с титулом, поля «Учебный год» и «Образовательная программа», "
            "подпись автора, одна точка сдачи. С copy_from копия выбранной версии с новыми id (пустой реестр "
            "выпусков, атрибуция источника в манифесте). Id пака: строчная латиница и цифры через дефис, "
            "уникален в пространстве и в каталоге Студии (pack_id_taken). Пример: "
            '{"workspace_id": "<uuid>", "pack_id": "spbu-cs", "name": {"ru": "СПбГУ", "en": "SPbU"}, '
            '"template_id": "coursework", "template_name": {"ru": "Курсовая", "en": "Course paper"}}.'
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "pack_id": {"type": "string", "description": "Id и папка пака"},
                "name": _LOCALIZED_TEXT,
                "description": _LOCALIZED_TEXT,
                "maintainer_name": {"type": "string", "description": "По умолчанию из профиля"},
                "maintainer_email": {"type": "string"},
                "license": {"type": "string", "description": "SPDX, по умолчанию Apache-2.0"},
                "source": {"type": "string", "description": "Адрес репозитория пака"},
                "template_id": {"type": "string", "description": "Id и папка первого шаблона"},
                "template_name": _LOCALIZED_TEXT,
                "template_short_name": _LOCALIZED_TEXT,
                "copy_from": _SCAFFOLD_SOURCE,
                "version": {"type": "string", "description": "Номер первой версии, по умолчанию <год>.1"},
            },
            ("workspace_id", "pack_id", "name", "template_id", "template_name"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        service = await self._deps.get(PackScaffoldService)
        maintainer_name = optional_text(args, "maintainer_name")
        if maintainer_name is None:
            default = (await service.options(actor, workspace_id)).maintainer
        else:
            default = Maintainer(name=maintainer_name, email=optional_text(args, "maintainer_email") or "")
        pack = NewPack(
            id=text_arg(args, "pack_id"),
            name=_text_pair(args, "name") or {},
            description=_text_pair(args, "description"),
            maintainer=default,
            license=optional_text(args, "license") or "",
            source=optional_text(args, "source"),
            template=_new_template(args),
        )
        result = await service.create_pack(
            actor,
            workspace_id,
            CreatePackInput(pack=pack, scaffold=_scaffold(args), version=optional_text(args, "version")),
        )
        return json_result(_created(result))


class PackNewTemplateTool(PackTool):
    spec = ToolSpec(
        name="pack_new_template",
        description=(
            "Студия шаблонов: новый шаблон в существующем паке пространства с черновой версией beta: заготовка "
            "«Минимальный» или копия версии (copy_from, варианты в pack_scaffold_options). Id шаблона: строчная "
            "латиница и цифры через дефис или подчёркивание, свободный в паке (template_id_taken)."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "pack": {"type": "string", "description": "Папка пака"},
                "template_id": {"type": "string"},
                "template_name": _LOCALIZED_TEXT,
                "template_short_name": _LOCALIZED_TEXT,
                "copy_from": _SCAFFOLD_SOURCE,
                "version": {"type": "string", "description": "Номер первой версии, по умолчанию <год>.1"},
            },
            ("workspace_id", "pack", "template_id", "template_name"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        result = await (await self._deps.get(PackScaffoldService)).create_template(
            actor,
            uuid_arg(args, "workspace_id"),
            text_arg(args, "pack"),
            CreateTemplateInput(
                template=_new_template(args), scaffold=_scaffold(args), version=optional_text(args, "version")
            ),
        )
        return json_result(_created(result))
