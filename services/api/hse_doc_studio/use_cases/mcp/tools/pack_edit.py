"""Правка файлов и форм версии через MCP: точечные правки YAML по JSON Pointer, удаление и перенос файлов, дерево,
модель версии и её операции, подсказки редактора, библиотека документов, профили сдачи.

Тулы зовут те же службы, что маршруты Студии (`PackFilesService`, `PackModelService`, `PackSubmissionService`,
`PackInsightService`): запись под замком пространства, `If-Match` по etag файла (`stale_file`), защита выпущенных версий
(`version_released`, подсказка `pack_new_version`) и реестров (`releases_read_only`). Точечная правка `pack_patch_yaml`
меняет только названные узлы, остальной текст (комментарии, порядок, кавычки) остаётся байт в байт; манифесты версии
и документов (`version.yaml`, `files/<документ>/doc.yaml`) проходят ту же проверку лоадера и схемы, что формы
(`model_invalid`, файл не меняется), прочие YAML после записи проверяются схемой (`findings`). Удаление файла и папки
и документа из версии требует `confirm: true`: без него тул описывает последствия и ничего не меняет.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Final

import yaml

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.model import ModelAction, ModelActionKind
from hse_doc_studio.core.pack_studio.paths import is_yaml, version_ref_of
from hse_doc_studio.core.pack_studio.submission import (
    ProfileHead,
    SubmissionList,
    SubmissionOp,
    SubmissionOpKind,
    VersionSubmission,
)
from hse_doc_studio.use_cases.mcp.tools._base import (
    ArgumentError,
    bool_arg,
    etag_arg,
    int_arg,
    jsonable,
    optional_text,
    text_arg,
    uuid_arg,
)
from hse_doc_studio.use_cases.mcp.tools.pack_outcome_view import loc
from hse_doc_studio.use_cases.mcp.tools.pack_submission_view import routes_lines, submission_lines
from hse_doc_studio.use_cases.mcp.tools.pack_view import (
    CONFIRM_PROP,
    FORMAT_PROP,
    clip_text,
    coded_error,
    confirmed,
    layout_arg,
    layout_result,
)
from hse_doc_studio.use_cases.mcp.tools.packs import _PATH, _VERSION, _WORKSPACE_ID, PackTool, _schema, version_arg
from hse_doc_studio.use_cases.pack_studio.files import MAX_YAML_OPS, PackFilesService, YamlOp
from hse_doc_studio.use_cases.pack_studio.insight import PackInsightService
from hse_doc_studio.use_cases.pack_studio.model import _MODEL_FILE, ModelView, PackModelService
from hse_doc_studio.use_cases.pack_studio.submission import PackSubmissionService

_MAX_FILES: Final = 200
_MAX_SUBMISSION_OPS: Final = 50
# Текст профилей сдачи с маршрутами: записанный порядок каждой точки и «Маршрут в этой комбинации» по шагам.
_SUBMISSION_CHARS: Final = 16_000
_OPS = ("set", "remove", "insert", "move")
_POINTER_NOTE: Final = (
    "pointer: JSON Pointer по узлам YAML («/meta_fields/0/label/ru», «~1» это «/», «~0» это «~»); числовое звено "
    "это индекс списка. Для числового ключа словаря вместо pointer дайте path: массив звеньев, строки остаются "
    "ключами, числа индексами."
)


def _tokens(pointer: str) -> tuple[str | int, ...]:
    if pointer in {"", "/"}:
        return ()
    if not pointer.startswith("/"):
        raise ArgumentError(
            localized_error(f"pointer {pointer!r}: должен начинаться с «/»", f"pointer {pointer!r} must start with '/'")
        )
    out: list[str | int] = []
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        out.append(int(token) if token.isdigit() else token)
    return tuple(out)


def _walk(data: Any, path: Sequence[str | int]) -> Any:
    for step in path:
        if isinstance(data, list) and isinstance(step, int) and step < len(data):
            data = data[step]
        elif isinstance(data, dict) and (step in data or str(step) in data):
            data = data[step] if step in data else data[str(step)]
        else:
            raise KeyError(step)
    return data


def _yaml_ops(raw: object, text: str | None) -> list[YamlOp]:  # noqa: C901 — разбор четырёх операций
    """Операции `set`, `remove`, `insert`, `move` в правки редактора YAML. `text` нужен для «-» (в конец списка)."""
    if not isinstance(raw, list) or not raw:
        raise ArgumentError(localized_error("ops: непустой список", "ops: a non-empty list is expected"))
    if len(raw) > MAX_YAML_OPS:
        raise ArgumentError(localized_error(f"ops: не больше {MAX_YAML_OPS}", f"ops: at most {MAX_YAML_OPS}"))
    ops: list[YamlOp] = []
    for number, item in enumerate(raw):
        if not isinstance(item, Mapping) or item.get("op") not in _OPS:
            raise ArgumentError(
                localized_error(
                    f"ops[{number}].op: одно из {', '.join(_OPS)}", f"ops[{number}].op: one of {', '.join(_OPS)}"
                )
            )
        explicit = item.get("path")
        if explicit is not None:
            if not isinstance(explicit, list) or not all(
                isinstance(p, str | int) and not isinstance(p, bool) for p in explicit
            ):
                raise ArgumentError(
                    localized_error(
                        f"ops[{number}].path: массив строк и чисел",
                        f"ops[{number}].path: an array of strings and numbers",
                    )
                )
            path: tuple[str | int, ...] = tuple(explicit)
        else:
            path = _tokens(str(item.get("pointer", "")))
        kind = item["op"]
        if kind == "set":
            if "value" not in item:
                raise ArgumentError(
                    localized_error(f"ops[{number}]: set требует value", f"ops[{number}]: set needs value")
                )
            ops.append(YamlOp("set", path, value=item["value"]))
        elif kind == "remove":
            if not path:
                raise ArgumentError(
                    localized_error(f"ops[{number}]: remove требует pointer", f"ops[{number}]: remove needs a pointer")
                )
            ops.append(YamlOp("delete", path))
        else:
            ops.append(_list_op(number, kind, item, path, text))
    return ops


def _list_op(
    number: int, kind: str, item: Mapping[str, object], path: tuple[str | int, ...], text: str | None
) -> YamlOp:
    """`insert`: pointer на список и `index` (или pointer на место в списке, «-» в конец); `move`: pointer на
    элемент списка и `to`."""
    index = item.get("index")
    if kind == "move":
        to = item.get("to")
        if not path or not isinstance(path[-1], int) or not isinstance(to, int) or isinstance(to, bool):
            raise ArgumentError(
                localized_error(
                    f"ops[{number}]: move: pointer на элемент списка и to",
                    f"ops[{number}]: move: a pointer to a list item and to",
                )
            )
        return YamlOp("move", path[:-1], index=path[-1], to=to)
    if isinstance(index, int) and not isinstance(index, bool):
        parent = path
    elif path and isinstance(path[-1], int):
        parent, index = path[:-1], path[-1]
    else:
        # «-» или pointer на сам список: в конец; длину берём из текста файла.
        parent = path[:-1] if path and path[-1] == "-" else path
        try:
            index = len(_walk(yaml.safe_load(text or ""), parent))
        except (KeyError, TypeError, yaml.YAMLError):
            raise ArgumentError(
                localized_error(
                    f"ops[{number}]: insert: pointer не указывает на список",
                    f"ops[{number}]: insert: the pointer is not a list",
                )
            ) from None
    if "value" not in item:
        raise ArgumentError(
            localized_error(f"ops[{number}]: insert требует value", f"ops[{number}]: insert needs value")
        )
    return YamlOp("insert", tuple(parent), value=item["value"], index=int(index))


def _write_data(path: str, written: Any) -> dict[str, object]:
    return {"path": path, "etag": written.etag, "size": written.size}


class PackPatchYamlTool(PackTool):
    spec = ToolSpec(
        name="pack_patch_yaml",
        description=(
            "Студия шаблонов: точечная правка YAML-файла пака по JSON Pointer без переписывания файла: комментарии, "
            "порядок и оформление остаются. ops (до 200, весь набор или ничего): set (value по pointer; создаёт "
            "ключ), remove, insert (value в список по pointer на список и index, либо pointer на место, «-» в "
            "конец), move (pointer на элемент списка и to). " + _POINTER_NOTE + " Пример: "
            '{"path": "<пак>/templates/<шаблон>/versions/<в>/version.yaml", "ops": [{"op": "set", '
            '"pointer": "/meta_fields/0/label/ru", "value": "Тема"}, {"op": "insert", "pointer": "/meta_fields/-", '
            '"value": {"key": "area", "type": "text"}}]}. if_match (etag из pack_read_file или прошлой правки) '
            "защищает от чужой правки (stale_file). Манифесты версии и документов проверяются лоадером и схемой: "
            "ломающая правка не пишется (model_invalid). Выпущенная версия: version_released, нужен "
            "pack_new_version. Ответ: новый etag, а у манифестов версии находки проверки."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "path": _PATH,
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": list(_OPS)},
                            "pointer": {"type": "string"},
                            "path": {"type": "array", "items": {"type": ["string", "integer"]}},
                            "value": {},
                            "index": {"type": "integer"},
                            "to": {"type": "integer"},
                        },
                        "required": ["op"],
                    },
                },
                "if_match": {"type": "string", "description": "Etag файла, на который опирается правка"},
                "format": FORMAT_PROP,
            },
            ("workspace_id", "path", "ops"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        path = text_arg(args, "path").strip("/")
        if not is_yaml(path):
            raise PackStudioError(PackStudioErrorCode.not_yaml)
        files = await self._deps.get(PackFilesService)
        if_match = etag_arg(args)
        raw = args.get("ops")
        needs_text = isinstance(raw, list) and any(isinstance(o, Mapping) and o.get("op") == "insert" for o in raw)
        text: str | None = None
        if needs_text:
            current = await files.read(actor, workspace_id, path)
            text = current.content.decode("utf-8", errors="replace")
            if_match = if_match or current.etag
        ops = _yaml_ops(raw, text)
        ref = version_ref_of(path)
        data: dict[str, Any]
        findings: list[Any] = []
        if ref is not None and _MODEL_FILE.match(ref.rest):
            view = await (await self._deps.get(PackModelService)).patch(
                actor, workspace_id, ref.pack, ref.template, ref.version, ref.rest, ops, if_match
            )
            etag = (
                view.model.manifest.etag
                if ref.rest == "version.yaml"
                else (await files.read(actor, workspace_id, path)).etag
            )
            data = {"path": path, "etag": etag}
        else:
            written = await files.patch_yaml(actor, workspace_id, path, ops, if_match)
            data = _write_data(path, written)
            report = await (await self._deps.get(PackInsightService)).lint(actor, workspace_id, path)
            findings = [jsonable(f) for f in report.findings[:20]]
        data["ops"] = len(ops)
        data["findings"] = findings
        text_out = f"Применено правок: {len(ops)}; etag {data['etag']}"
        text_out += "".join(f"\n  {f.get('severity')}: {f.get('message')}" for f in findings)
        text_out += "\nПроверьте версию: pack_lint."
        return layout_result(layout_arg(args), text_out, data)


class PackDeleteFileTool(PackTool):
    spec = ToolSpec(
        name="pack_delete_file",
        description=(
            "Студия шаблонов: удалить файл или папку целиком из пространства. ДЕСТРУКТИВНО: без confirm: true "
            "ничего не делает и описывает последствия. Выпущенные версии и реестры выпусков не удаляются "
            "(version_released, releases_read_only). Удалённое можно вернуть из git только если оно было в коммите. "
            "if_match (etag) защищает от удаления чужой правки (stale_file); для папки не нужен."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "path": _PATH,
                "if_match": {"type": "string"},
                "confirm": CONFIRM_PROP,
                "format": FORMAT_PROP,
            },
            ("workspace_id", "path"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        path = text_arg(args, "path").strip("/")
        files = await self._deps.get(PackFilesService)
        if not confirmed(args):
            info: dict[str, object] = {"path": path}
            try:
                found = await files.read(actor, workspace_id, path)
                info.update(size=len(found.content), read_only=found.read_only, etag=found.etag)
            except PackStudioError as exc:
                if exc.code is not PackStudioErrorCode.file_not_found:
                    raise
                info["note"] = "файла нет: путь либо папка, либо отсутствует"
            hint = localized_error(
                "Ничего не удалено. Покажите человеку путь и повторите с confirm: true.",
                "Nothing was deleted. Show the person the path and repeat with confirm: true.",
            )
            data = {"confirm_required": True, **info, "hint": hint}
            return layout_result(layout_arg(args), f"Удалить {path}? {hint}", data)
        await files.delete(actor, workspace_id, path, etag_arg(args))
        return layout_result(layout_arg(args), f"Удалено: {path}", {"deleted": True, "path": path})


class PackMoveFileTool(PackTool):
    spec = ToolSpec(
        name="pack_move_file",
        description=(
            "Студия шаблонов: перенести или переименовать файл внутри пространства (запись в новое место и "
            "удаление старого, под защитой выпущенных версий для обоих путей). Папки не переносятся. Новое место "
            "занято: file_exists, если не overwrite: true. if_match (etag исходного файла) защищает от чужой правки."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "src": _PATH,
                "dst": _PATH,
                "overwrite": {"type": "boolean", "default": False},
                "if_match": {"type": "string"},
                "format": FORMAT_PROP,
            },
            ("workspace_id", "src", "dst"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        src, dst = text_arg(args, "src").strip("/"), text_arg(args, "dst").strip("/")
        files = await self._deps.get(PackFilesService)
        found = await files.read(actor, workspace_id, src)
        if etag_arg(args) not in {None, found.etag}:
            raise PackStudioError(PackStudioErrorCode.stale_file, etag=found.etag)
        if not bool_arg(args, "overwrite", False):
            try:
                await files.read(actor, workspace_id, dst)
            except PackStudioError as exc:
                if exc.code is not PackStudioErrorCode.file_not_found:
                    raise
            else:
                return coded_error(
                    "file_exists",
                    "Место занято: overwrite: true или другой dst.",
                    "The target exists: use overwrite: true or another dst.",
                    path=dst,
                )
        written = await files.write(actor, workspace_id, dst, found.content, None)
        await files.delete(actor, workspace_id, src, found.etag)
        data = {"moved": True, "from": src, "to": dst, "etag": written.etag, "size": written.size}
        return layout_result(layout_arg(args), f"Перенесено: {src} -> {dst}", data)


def _versions_text(tree: Any, limit: int) -> list[str]:
    lines: list[str] = []
    for pack in tree.packs:
        lines.append(f"{pack.id}")
        for template in pack.templates:
            lines.append(f"  {pack.id}/{template.id}")
            for v in template.versions[:limit]:
                flag = "released" if v.released else "draft"
                lines.append(f"    {v.version} {flag}{' *' if v.modified else ''}")
    return lines


class PackTreeTool(PackTool):
    spec = ToolSpec(
        name="pack_tree",
        description=(
            "Студия шаблонов: дерево файлов пространства (то, что видно в проводнике): паки, шаблоны, версии со "
            "статусом (released, draft, * изменена) и файлы с размером и read_only (version_released, "
            "releases_read_only). prefix: показать файлы только под путём (по умолчанию дерево без файлов); "
            "max_files до 200."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "prefix": {"type": "string", "description": "Путь папки: показать её файлы"},
                "max_files": {"type": "integer", "default": 100},
                "format": FORMAT_PROP,
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        view = await (await self._deps.get(PackFilesService)).tree(actor, uuid_arg(args, "workspace_id"))
        tree = view.tree
        prefix = (optional_text(args, "prefix") or "").strip("/")
        limit = int_arg(args, "max_files", 100, lo=1, hi=_MAX_FILES)
        shown = [f for f in tree.files if prefix and (f.path == prefix or f.path.startswith(prefix + "/"))][:limit]
        lines = _versions_text(tree, 50)
        if prefix:
            lines.append(f"Файлы под {prefix}: {len(shown)}")
            lines += [
                f"  {'d' if f.is_dir else 'f'} {f.path} {f.size}{' [' + f.read_only + ']' if f.read_only else ''}"
                for f in shown
            ]
        data = {
            "base_sha": view.workspace.base_sha,
            "packs": jsonable(tree.packs),
            "files": [jsonable(f) for f in shown],
            "files_total": len(tree.files),
            "truncated": tree.truncated,
        }
        return layout_result(layout_arg(args), "\n".join(lines), data, truncated=tree.truncated)


def _model_data(view: ModelView) -> dict[str, Any]:
    model = view.model
    return {
        "read_only": view.read_only,
        "manifest": {"path": model.manifest.path, "etag": model.manifest.etag, "data": model.manifest.data},
        "documents": [
            {
                "id": d.id,
                "manifest": None if d.manifest is None else {"path": d.manifest.path, "etag": d.manifest.etag},
                "data": d.data,
                "files": [jsonable(f) for f in d.files],
                "references": list(d.references),
            }
            for d in model.documents
        ],
        "usage": [jsonable(u) for u in model.usage],
        "checks": list(model.checks),
        "problems": list(model.problems),
        "changed": list(view.changed),
    }


def _model_text(view: ModelView, head: str) -> str:
    model = view.model
    lines = [
        head,
        f"version.yaml etag {model.manifest.etag}" + (f"; только чтение: {view.read_only}" if view.read_only else ""),
    ]
    for d in model.documents:
        etag = f" etag {d.manifest.etag}" if d.manifest is not None else ""
        lines.append(f"  документ {d.id}{etag}: файлов {len(d.files)}")
    lines.append(
        f"Использование полей: {len(model.usage)}; проверок: {len(model.checks)}; проблем: {len(model.problems)}"
    )
    lines += [f"  проблема: {p}" for p in list(model.problems)[:10]]
    return "\n".join(lines)


class PackModelTool(PackTool):
    spec = ToolSpec(
        name="pack_model",
        description=(
            "Студия шаблонов: модель версии для форм: манифест версии и doc.yaml документов как данные с etag "
            "каждого файла (для if_match у pack_patch_yaml), файлы документов по языкам, где печатается каждое "
            "поле анкеты (usage), проверки и проблемы лоадера. Текст показывает etag и счётчики; format json "
            "отдаёт данные манифестов. Отличие от pack_read: etag и usage."
        ),
        parameters=_schema(
            {"workspace_id": _WORKSPACE_ID, "version": _VERSION, "format": FORMAT_PROP}, ("workspace_id", "version")
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        view = await (await self._deps.get(PackModelService)).get(
            actor, uuid_arg(args, "workspace_id"), ref.pack, ref.template, ref.version
        )
        return layout_result(layout_arg(args), _model_text(view, f"{ref.dir}"), _model_data(view))


_MODEL_ACTIONS = tuple(k.value for k in ModelActionKind)


class PackModelActionTool(PackTool):
    spec = ToolSpec(
        name="pack_model_action",
        description=(
            "Студия шаблонов: операции форм на несколько файлов версии, как в редакторе версии. action: "
            "rename_field (field, to: новый ключ поля анкеты во всех шаблонах версии), add_document (document: "
            "id, name {ru, en}; source: папка документа-заготовки из pack_doc_library, иначе пустой документ), "
            "remove_document (document: ДЕСТРУКТИВНО, удаляет документ и его папку files/<id>/, нужен confirm: "
            "true), add_translation (document, lang, files). if_match: etag version.yaml (pack_model). Выпущенная "
            "версия: version_released."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "action": {"type": "string", "enum": list(_MODEL_ACTIONS)},
                "field": {"type": "string"},
                "to": {"type": "string"},
                "document": {"type": "string"},
                "name": {"type": "object"},
                "source": {"type": "string"},
                "lang": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}},
                "if_match": {"type": "string"},
                "confirm": CONFIRM_PROP,
                "format": FORMAT_PROP,
            },
            ("workspace_id", "version", "action"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        name = optional_text(args, "action")
        if name not in _MODEL_ACTIONS:
            raise ArgumentError(
                localized_error(
                    f"action: одно из {', '.join(_MODEL_ACTIONS)}", f"action: one of {', '.join(_MODEL_ACTIONS)}"
                )
            )
        if name == ModelActionKind.remove_document.value and not confirmed(args):
            hint = localized_error(
                f"Ничего не удалено. Документ {args.get('document')} и его папка files/ пропадут из версии "
                "(вернуть можно из git, если он был в коммите): покажите это человеку и повторите с "
                "confirm: true.",
                f"Nothing was deleted. Document {args.get('document')} and its files/ folder will be removed from the "
                "version (restorable from git if it was committed): show it to the person and repeat with "
                "confirm: true.",
            )
            return layout_result(layout_arg(args), hint, {"confirm_required": True, "hint": hint})
        names = args.get("name")
        files = args.get("files")
        action = ModelAction(
            kind=ModelActionKind(name),
            field=optional_text(args, "field"),
            to=optional_text(args, "to"),
            document=optional_text(args, "document"),
            name={str(k): str(v) for k, v in names.items()} if isinstance(names, Mapping) else None,
            source=optional_text(args, "source"),
            lang=optional_text(args, "lang"),
            files=tuple(str(f) for f in files) if isinstance(files, list) else (),
        )
        view = await (await self._deps.get(PackModelService)).act(
            actor,
            uuid_arg(args, "workspace_id"),
            ref.pack,
            ref.template,
            ref.version,
            action,
            etag_arg(args),
        )
        return layout_result(
            layout_arg(args),
            _model_text(view, f"Выполнено: {name}. Изменены файлы: {', '.join(view.changed)}"),
            _model_data(view),
        )


_TEAM_HINT: Final = (
    "Командный проект, строка каждого автора (якорь author__<слаг> на общем документе): pack_help (topic: team)."
)


class PackHintsTool(PackTool):
    spec = ToolSpec(
        name="pack_hints",
        description=(
            "Студия шаблонов: подсказки для правки .j2 и .tex: поля анкеты версии файла (ключ, тип, подпись) и "
            "макросы \\hse... её динамических инклудов с полями, которые они печатают. path: любой файл версии."
        ),
        parameters=_schema(
            {"workspace_id": _WORKSPACE_ID, "path": _PATH, "format": FORMAT_PROP}, ("workspace_id", "path")
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        hints = await (await self._deps.get(PackInsightService)).hints(
            actor, uuid_arg(args, "workspace_id"), text_arg(args, "path")
        )
        lang = current_interface_language().value
        lines = [f"Версия: {hints.version or 'путь вне версии, подсказок нет'}"]
        lines += [
            f"  поле {f.key} ({f.type}){': ' + loc(f.label, lang) if f.label else ''}"
            for f in hints.meta_fields[:_MAX_FILES]
        ]
        lines += [f"  макрос \\{m.name}: {', '.join(m.keys)} ({m.source})" for m in hints.macros[:_MAX_FILES]]
        if hints.version and str(args["path"]).rstrip("/").endswith((".tex", ".j2")):
            lines.append(_TEAM_HINT)
        return layout_result(layout_arg(args), "\n".join(lines), hints)


class PackDocLibraryTool(PackTool):
    spec = ToolSpec(
        name="pack_doc_library",
        description=(
            "Студия шаблонов: библиотека документов-заготовок пространства (последняя версия каждого шаблона): "
            "путь папки документа для source в pack_model_action с add_document."
        ),
        parameters=_schema({"workspace_id": _WORKSPACE_ID, "format": FORMAT_PROP}, ("workspace_id",)),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        found = await (await self._deps.get(PackModelService)).library(actor, uuid_arg(args, "workspace_id"))
        lang = current_interface_language().value
        text = (
            "\n".join(
                f'{d.path}  {d.id} "{loc(d.name, lang)}" ({d.pack}/{d.template}/{d.version})'
                for d in found[:_MAX_FILES]
            )
            or "Документов-заготовок нет."
        )
        return layout_result(layout_arg(args), text, {"documents": jsonable(found)})


def _submission_ops(raw: object) -> list[SubmissionOp]:
    if not isinstance(raw, list) or not 0 < len(raw) <= _MAX_SUBMISSION_OPS:
        raise ArgumentError(
            localized_error(f"ops: от 1 до {_MAX_SUBMISSION_OPS}", f"ops: 1 to {_MAX_SUBMISSION_OPS} operations")
        )
    ops: list[SubmissionOp] = []
    for number, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ArgumentError(localized_error(f"ops[{number}]: объект", f"ops[{number}]: an object is expected"))
        try:
            kind = SubmissionOpKind(str(item.get("op")))
            entries = SubmissionList(item["entries"]) if item.get("entries") is not None else None
        except ValueError:
            raise ArgumentError(
                localized_error(
                    f"ops[{number}]: op из {', '.join(k.value for k in SubmissionOpKind)}, entries из "
                    f"{', '.join(k.value for k in SubmissionList)}",
                    f"ops[{number}]: op is one of {', '.join(k.value for k in SubmissionOpKind)}, entries one of "
                    f"{', '.join(k.value for k in SubmissionList)}",
                )
            ) from None
        head = item.get("head")
        steps = item.get("steps")
        ops.append(
            SubmissionOp(
                op=kind,
                profile=item.get("profile"),
                head=ProfileHead(
                    str(head.get("id", "")),
                    dict(head.get("name") or {}),
                    dict(head.get("description") or {}),
                    dict(head["deadline_hint"]) if head.get("deadline_hint") else None,
                )
                if isinstance(head, Mapping)
                else None,
                entries=entries,
                index=item.get("index"),
                to=item.get("to"),
                value=item.get("value") if isinstance(item.get("value"), Mapping) else None,
                steps=tuple(tuple(str(p) for p in step) for step in steps) if isinstance(steps, list) else None,
            )
        )
    return ops


_SUB_PROPS: Final = {
    "workspace_id": _WORKSPACE_ID,
    "version": _VERSION,
    "format": FORMAT_PROP,
}


def _only_profile(sub: VersionSubmission, wanted: str) -> VersionSubmission:
    found = tuple(profile for profile in sub.profiles if profile.id == wanted)
    if not found:
        known = ", ".join(profile.id for profile in sub.profiles if profile.id) or "-"
        raise ArgumentError(
            localized_error(
                f"profile: нет профиля {wanted!r}, есть: {known}", f"profile: no {wanted!r}, known: {known}"
            )
        )
    return replace(sub, profiles=found)


async def _submission_reply(tool: PackTool, actor: Actor, args: dict[str, object], *, edit: bool) -> ToolResult:
    ref = version_arg(args)
    workspace_id = uuid_arg(args, "workspace_id")
    service = await tool._deps.get(PackSubmissionService)  # noqa: SLF001 — общий разбор двух тулов
    if edit:
        view = await service.edit(
            actor,
            workspace_id,
            ref.pack,
            ref.template,
            ref.version,
            _submission_ops(args.get("ops")),
            etag_arg(args),
        )
        head = f"Профили сдачи изменены. etag {view.etag}"
    else:
        view = await service.get(actor, workspace_id, ref.pack, ref.template, ref.version)
        head = f"{view.path} etag {view.etag}" + (f" [{view.read_only}]" if view.read_only else "")
    sub = view.submission
    wanted = None if edit else optional_text(args, "profile")
    if wanted is not None:
        sub = _only_profile(sub, wanted)
    lines = [head, f"Документы: {', '.join(sub.documents)}", f"Слоты: {', '.join(s.id for s in sub.slots)}"]
    lines += submission_lines(sub, current_interface_language().value)
    data: dict[str, Any] = {
        "path": view.path,
        "etag": view.etag,
        "read_only": view.read_only,
        "submission": jsonable(sub),
    }
    if not edit and bool_arg(args, "routes", False):
        combo = args.get("combination")
        routes = await service.routes(
            actor,
            workspace_id,
            ref.pack,
            ref.template,
            ref.version,
            optional_text(args, "example"),
            {str(k): str(v) for k, v in combo.items()} if isinstance(combo, Mapping) else None,
        )
        if wanted is not None:
            routes = replace(routes, profiles=tuple(r for r in routes.profiles if r.id == wanted))
        data["routes"] = jsonable(routes)
        lines += routes_lines(routes)
    text, cut = clip_text("\n".join(lines), _SUBMISSION_CHARS)
    return layout_result(layout_arg(args), text, data, truncated=cut)


class PackSubmissionTool(PackTool):
    spec = ToolSpec(
        name="pack_submission",
        description=(
            "Студия шаблонов: профили сдачи версии (точки контроля: пункты документов, лишние файлы, слоты "
            "подписей, порядок маршрута), слоты и анкеты каталога, etag version.yaml для pack_submission_edit. "
            "Текст показывает записанный маршрут каждой точки: порядок по шагам (signing_route, иначе порядок "
            "версии или встроенный), подписи пунктов, слоты сверх точки с условием when и отметкой "
            "«необязательна». routes: true (с example и combination) добавляет маршрут каждого профиля в "
            "комбинации: шаги людьми, кто какую подпись ставит, что условие не пропустило. Итог для вводных "
            "смотрите pack_outcome. profile (id точки) оставляет в тексте и json только эту точку сдачи, и записанную, "
            "и посчитанную: весь ответ с routes большой. Только чтение."
        ),
        parameters=_schema(
            {
                **_SUB_PROPS,
                "routes": {"type": "boolean", "default": False},
                "example": {"type": "string"},
                "combination": {"type": "object"},
                "profile": {"type": "string", "description": "Id профиля сдачи: только эта точка; без него все"},
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        return await _submission_reply(self, actor, args, edit=False)


class PackSubmissionEditTool(PackTool):
    spec = ToolSpec(
        name="pack_submission_edit",
        description=(
            "Студия шаблонов: правка профилей сдачи в version.yaml формами. ops (до 50, весь набор или ничего): "
            "add_profile и set_profile (head {id, name, description, deadline_hint}; profile: индекс), "
            "remove_profile, move_profile (to), set_profile_route и set_route (steps: [[persona,...],...]; без "
            "steps: сброс к порядку по умолчанию), add_entry, set_entry, remove_entry, move_entry для entries "
            "items, extra_items и signing_slots (value: запись, index, to). if_match: etag из pack_submission. "
            "Выпущенная версия: version_released. Некорректное: submission_invalid, файл не меняется."
        ),
        parameters=_schema(
            {
                **_SUB_PROPS,
                "ops": {"type": "array", "items": {"type": "object"}},
                "if_match": {"type": "string"},
            },
            ("workspace_id", "version", "ops"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        return await _submission_reply(self, actor, args, edit=True)


__all__ = [
    "PackDeleteFileTool",
    "PackDocLibraryTool",
    "PackHintsTool",
    "PackModelActionTool",
    "PackModelTool",
    "PackMoveFileTool",
    "PackPatchYamlTool",
    "PackSubmissionEditTool",
    "PackSubmissionTool",
    "PackTreeTool",
]
