"""Формы версии, которых не было у MCP (pack-studio-mcp.md, срез B): правила проверки и номер версии.

- `pack_checks`: файлы правил `checks/*.yaml` и `checks_version` формой, тем же `PackChecksFormService`, что маршруты
  `.../checks` (чтение, `PATCH .../checks/files/{name}`, `PUT .../checks/config`): защита выпущенных версий, `If-Match`,
  весь набор правок или ничего (`checks_invalid` с причиной).
- `pack_version_number`: «Изменить номер» черновика (`POST .../renumber`) и «Перенести правки в новую версию»
  (`POST .../move-edits`) тем же `PackVersionService`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import TemplateUpdateClass, ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.pack_studio.checks_form import (
    MAX_CHECKS_OPS,
    OVERRIDE_SEVERITIES,
    RULE_SEVERITIES,
    STRUCTURAL_CHECKS,
    ChecksConfig,
    ChecksHeader,
    ChecksOp,
    ChecksOpKind,
    RuleEntry,
)
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, optional_text, text_arg, uuid_arg
from hse_doc_studio.use_cases.mcp.tools.pack_view import FORMAT_PROP, layout_arg, layout_result
from hse_doc_studio.use_cases.mcp.tools.packs import (
    _VERSION,
    _WORKSPACE_ID,
    PackTool,
    _schema,
    _state,
    _update_class,
    version_arg,
)
from hse_doc_studio.use_cases.pack_studio.checks_form import ChecksView, PackChecksFormService
from hse_doc_studio.use_cases.pack_studio.versions import PackVersionService

_LOCALIZED: Final = {"type": "object", "description": "Текст по языкам: {ru, en}"}
_RULE: Final = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Id правила; префикс это имя файла правил"},
        "title": _LOCALIZED,
        "description": _LOCALIZED,
        "category": {"type": "string"},
        "applies_to": {"type": ["array", "null"], "items": {"type": "string"}, "description": "null: все документы"},
        "default_severity": {"type": "string", "enum": list(RULE_SEVERITIES)},
        "engine": {"type": "string", "description": "Движок проверки: structural, regex, python и др."},
        "params": {"type": "object", "description": f"Параметры движка; structural: check из {STRUCTURAL_CHECKS}"},
    },
    "required": ["id", "title", "default_severity", "engine"],
}


def _localized(raw: object, key: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error(f"{key}: ожидается {{ru, en}}", f"{key}: {{ru, en}} is expected"))
    return {str(k): str(v) for k, v in raw.items()}


def _rule(raw: object) -> RuleEntry | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error("rule: ожидается объект", "rule: an object is expected"))
    applies = raw.get("applies_to")
    params = raw.get("params") or {}
    if not isinstance(params, Mapping):
        raise ArgumentError(localized_error("rule.params: ожидается объект", "rule.params: an object is expected"))
    category = raw.get("category")
    return RuleEntry(
        id=text_arg(raw, "id"),
        title=_localized(raw.get("title"), "rule.title"),
        description=_localized(raw.get("description"), "rule.description"),
        category=str(category) if isinstance(category, str) and category else None,
        applies_to=tuple(str(a) for a in applies) if isinstance(applies, list) else None,
        default_severity=text_arg(raw, "default_severity"),
        engine=text_arg(raw, "engine"),
        params={str(k): v for k, v in params.items()},
    )


def _header(raw: object) -> ChecksHeader | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error("header: ожидается объект", "header: an object is expected"))
    url = raw.get("url")
    return ChecksHeader(
        label=_localized(raw.get("label"), "header.label"),
        ref=_localized(raw.get("ref"), "header.ref"),
        source=_localized(raw.get("source"), "header.source"),
        url=str(url) if isinstance(url, str) and url else None,
    )


def _index(raw: Mapping[str, object], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def checks_ops(raw: object) -> list[ChecksOp]:
    """Правки файла правил из аргумента `ops` (тот же вид, что тело `PATCH .../checks/files/{name}`)."""
    if not isinstance(raw, list) or not 0 < len(raw) <= MAX_CHECKS_OPS:
        raise ArgumentError(
            localized_error(f"ops: список из 1..{MAX_CHECKS_OPS} правок", f"ops: a list of 1..{MAX_CHECKS_OPS} edits")
        )
    ops: list[ChecksOp] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ArgumentError(localized_error("ops: ожидается список объектов", "ops: a list of objects"))
        try:
            kind = ChecksOpKind(str(item.get("op")))
        except ValueError:
            names = ", ".join(k.value for k in ChecksOpKind)
            raise ArgumentError(localized_error(f"op: одно из {names}", f"op: one of {names}")) from None
        op = ChecksOp(
            op=kind,
            header=_header(item.get("header")),
            index=_index(item, "index"),
            to=_index(item, "to"),
            rule=_rule(item.get("rule")),
        )
        if kind is ChecksOpKind.set_header and op.header is None:
            raise ArgumentError(localized_error("set_header: нужен header", "set_header needs header"))
        if kind in {ChecksOpKind.add_rule, ChecksOpKind.set_rule} and op.rule is None:
            raise ArgumentError(localized_error(f"{kind.value}: нужен rule", f"{kind.value} needs rule"))
        ops.append(op)
    return ops


def _strings(raw: object, key: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ArgumentError(localized_error(f"{key}: ожидается список строк", f"{key}: a list of strings"))
    return tuple(str(item) for item in raw)


def checks_config(raw: object) -> ChecksConfig:
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error("config: ожидается объект", "config: an object is expected"))
    override = raw.get("severity_override") or {}
    if not isinstance(override, Mapping) or any(str(v) not in OVERRIDE_SEVERITIES for v in override.values()):
        raise ArgumentError(
            localized_error(
                f"severity_override: {{id правила: одно из {OVERRIDE_SEVERITIES}}}",
                f"severity_override: {{rule id: one of {OVERRIDE_SEVERITIES}}}",
            )
        )
    return ChecksConfig(
        disabled_categories=_strings(raw.get("disabled_categories"), "disabled_categories"),
        disabled=_strings(raw.get("disabled"), "disabled"),
        severity_override={str(k): str(v) for k, v in override.items()},
    )


def _view(view: ChecksView) -> dict[str, Any]:
    config = view.config
    return {
        "version": view.ref.dir,
        "documents": list(view.documents),
        "files": [
            {
                "name": f.name,
                "path": f.path,
                "etag": f.etag,
                "read_only": f.read_only,
                "header": {"label": f.view.header.label, "ref": f.view.header.ref, "url": f.view.header.url},
                "prefix": f.view.prefix,
                "error": f.view.error,
                "rules": [
                    {
                        "index": r.index,
                        "error": r.error,
                        **(
                            {
                                "id": r.entry.id,
                                "title": dict(r.entry.title),
                                "category": r.entry.category,
                                "applies_to": list(r.entry.applies_to) if r.entry.applies_to is not None else None,
                                "default_severity": r.entry.default_severity,
                                "engine": r.entry.engine,
                                "params": dict(r.entry.params),
                            }
                            if r.entry is not None
                            else {}
                        ),
                    }
                    for r in f.view.rules
                ],
            }
            for f in view.files
        ],
        "config": {
            "path": config.path,
            "etag": config.etag,
            "read_only": config.read_only,
            "disabled_categories": list(config.config.disabled_categories),
            "disabled": list(config.config.disabled),
            "severity_override": dict(config.config.severity_override or {}),
        },
    }


def _text(data: Mapping[str, Any]) -> str:
    lines = [f"Правила проверки {data['version']}: файлов {len(data['files'])}"]
    for f in data["files"]:
        lines.append(f"- {f['name']} (etag {f['etag']}{', ' + f['read_only'] if f['read_only'] else ''})")
        for r in f["rules"][:60]:
            if r.get("error"):
                lines.append(f"    [{r['index']}] ошибка: {r['error']}")
            else:
                title = r["title"].get("ru") or next(iter(r["title"].values()), "")
                lines.append(f"    [{r['index']}] {r['id']} ({r['engine']}, {r['default_severity']}): {title}")
    cfg = data["config"]
    lines.append(
        f"checks_version (etag {cfg['etag']}): выключены категории {cfg['disabled_categories']}, правила "
        f"{cfg['disabled']}, важность {cfg['severity_override']}"
    )
    return "\n".join(lines)


class PackChecksTool(PackTool):
    spec = ToolSpec(
        name="pack_checks",
        description=(
            "Студия шаблонов: правила проверки версии (нормоконтроль) формой, как «Содержимое, Правила проверки». "
            "Без file и config показывает файлы checks/*.yaml (шапка, правила по index) и checks_version с etag. "
            "file с ops правит файл правил (set_header, add_rule, set_rule и remove_rule по index, move_rule с to); "
            "config пишет checks_version (disabled_categories, disabled, severity_override: info, warn, err, "
            "skipped). Весь набор или ничего (checks_invalid с reason); if_match: etag файла или version.yaml. "
            "Выпущенная версия: version_released. Пример: "
            '{"file": "gost.yaml", "ops": [{"op": "set_rule", "index": 0, "rule": {"id": "gost.margins", '
            '"title": {"ru": "Поля"}, "default_severity": "err", "engine": "structural", "params": '
            '{"check": "page_geometry"}}}]}.'
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "file": {"type": "string", "description": "Имя файла правил в checks/, например gost.yaml"},
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": [k.value for k in ChecksOpKind]},
                            "index": {"type": "integer"},
                            "to": {"type": "integer"},
                            "header": {"type": "object", "description": "label, ref, source ({ru, en}), url"},
                            "rule": _RULE,
                        },
                        "required": ["op"],
                    },
                },
                "config": {
                    "type": "object",
                    "properties": {
                        "disabled_categories": {"type": "array", "items": {"type": "string"}},
                        "disabled": {"type": "array", "items": {"type": "string"}},
                        "severity_override": {"type": "object"},
                    },
                    "description": "checks_version версии целиком",
                },
                "if_match": {"type": "string", "description": "Etag файла правил или version.yaml"},
                "format": FORMAT_PROP,
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        workspace_id = uuid_arg(args, "workspace_id")
        service = await self._deps.get(PackChecksFormService)
        if_match = optional_text(args, "if_match")
        file = optional_text(args, "file")
        if file is not None and args.get("config") is not None:
            raise ArgumentError(localized_error("file и config по отдельности", "file and config one at a time"))
        if file is not None:
            ops = checks_ops(args.get("ops"))
            view = await service.edit_file(
                actor, workspace_id, ref.pack, ref.template, ref.version, file, ops, if_match
            )
        elif args.get("config") is not None:
            config = checks_config(args.get("config"))
            view = await service.edit_config(actor, workspace_id, ref.pack, ref.template, ref.version, config, if_match)
        else:
            view = await service.get(actor, workspace_id, ref.pack, ref.template, ref.version)
        data = _view(view)
        return layout_result(layout_arg(args), _text(data), data)


_ACTIONS: Final = ("renumber", "move_edits")


class PackVersionNumberTool(PackTool):
    spec = ToolSpec(
        name="pack_version_number",
        description=(
            "Студия шаблонов: номер версии. action renumber: черновик получает новый номер (to явно, ГОД.MINOR.PATCH, "
            "или update_class: номер этого класса из pack_classify), мягче минимума класса нельзя "
            "(class_softer_than_changes). action move_edits: правки, сделанные в выпущенной версии мимо Студии "
            "(pack_classify: modified, move_to), уходят в новую версию (to или следующий свободный номер), а у git "
            "выпущенный каталог возвращается к выпуску."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "action": {"type": "string", "enum": list(_ACTIONS)},
                "to": {"type": "string", "description": "Новый номер, например 2026.2.0"},
                "update_class": {"type": "string", "enum": ["patch", "minor", "major"]},
            },
            ("workspace_id", "version", "action"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        workspace_id = uuid_arg(args, "workspace_id")
        action = text_arg(args, "action")
        if action not in _ACTIONS:
            raise ArgumentError(localized_error("action: renumber или move_edits", "action: renumber or move_edits"))
        service = await self._deps.get(PackVersionService)
        to = optional_text(args, "to")
        update_class = _update_class(args, "update_class")
        if action == "renumber":
            if to is None:
                if update_class is None:
                    raise ArgumentError(localized_error("укажите to или update_class", "pass to or update_class"))
                state = await service.state(actor, workspace_id, ref.pack, ref.template, ref.version)
                to = _numbers(state.numbers).get(update_class.value)
                if to is None:
                    raise ArgumentError(localized_error("для класса нет номера", "no number for the class"))
            moved = await service.renumber(actor, workspace_id, ref.pack, ref.template, ref.version, to)
        else:
            moved = await service.move_edits(actor, workspace_id, ref.pack, ref.template, ref.version, to)
        state = await service.state(actor, workspace_id, moved.ref.pack, moved.ref.template, moved.ref.version)
        return layout_result(
            "json",
            "",
            {
                "version": moved.ref.dir,
                "previous": moved.previous,
                "unreleased": moved.unreleased,
                "restored": moved.restored,
                "edited": list(moved.edited),
                "state": _state(state),
            },
        )


def _numbers(numbers: Mapping[Any, str]) -> dict[str, str]:
    return {
        str(k.value if isinstance(k, TemplateUpdateClass) else getattr(k, "value", k)): v for k, v in numbers.items()
    }
