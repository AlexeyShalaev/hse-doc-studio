"""Сценарии и обзоры результата версии через MCP: `pack_scenario_*`, `pack_outcome_atlas`, `pack_outcome_explain`,
`pack_outcome_matrix` (template-studio-outcome.md, 4.7, срезы O4 и O6).

Тулы зовут те же службы, что эндпоинты `scenarios*` и `outcome/{atlas,explain,matrix}` (`PackScenarioService`,
`PackAtlasService`, `PackOutcomeService`, `PackCompareService`), с теми же правами, областью токена `packs`,
защитой выпущенных версий и конфликтов (`If-Match` по etag файла сценария, `stale_file`) и теми же правилами частоты
(прогон и explain `pack_outcome`, атлас `pack_atlas`, матрица `pack_impact`). Записывают только файлы сценариев;
письма, подписи и приглашения расчёт не затрагивает. Ответ: компактный текст и структура (`format`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.atlas import decode_key
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, etag_arg, int_arg, optional_text, text_arg, uuid_arg
from hse_doc_studio.use_cases.mcp.tools.pack_outcome import (
    _SCENARIO,
    _STATE,
    _inputs_arg,
    _state_arg,
    outcome_hint,
)
from hse_doc_studio.use_cases.mcp.tools.pack_outcome_view import condition_of, loc
from hse_doc_studio.use_cases.mcp.tools.pack_view import FORMAT_PROP, layout_arg, layout_result
from hse_doc_studio.use_cases.mcp.tools.packs import (
    _VERSION,
    _WORKSPACE_ID,
    PackTool,
    _schema,
    refusal,
    version_arg,
)
from hse_doc_studio.use_cases.pack_studio.outcome_atlas import PackAtlasService
from hse_doc_studio.use_cases.pack_studio.outcome_compare import PackCompareService
from hse_doc_studio.use_cases.pack_studio.outcome_service import ExplainRequest, PackOutcomeService
from hse_doc_studio.use_cases.pack_studio.scenario_service import PackScenarioService, ScenarioEntry

_TEMPLATE = {
    "type": "string",
    "description": "Шаблон: «<пак>/<шаблон>» (имена папок), например «hse-cs-se/vkr»",
}
_MAX_GROUPS: Final = 50
_MAX_ROWS: Final = 200
_MAX_LINES: Final = 40
_SECTIONS: Final = ("documents", "meta", "forms", "participants", "points", "route", "checks")
_STATUS_RU: Final = {"passed": "совпало", "failed": "изменилось", "error": "ошибка", "unchecked": "не проверено"}
_STATUS_EN: Final = {"passed": "matched", "failed": "changed", "error": "error", "unchecked": "unchecked"}
_CELL: Final = {"matched": "ok", "changed": "chg", "unchecked": "--", "error": "err"}


def template_arg(args: Mapping[str, object], key: str = "template") -> tuple[str, str]:
    raw = text_arg(args, key).strip("/").split("/")
    if len(raw) != 2 or not all(raw):  # noqa: PLR2004
        raise ArgumentError(
            localized_error(f"{key}: ожидается «<пак>/<шаблон>»", f"{key}: «<pack>/<template>» is expected")
        )
    return raw[0], raw[1]


def _version_prop(purpose: str) -> dict[str, str]:
    forms = "номер («2026.2.0») или «<пак>/<шаблон>/<версия>» того же шаблона"
    return {"type": "string", "description": f"{purpose}: {forms}"}


def _version_number(args: Mapping[str, object], pack: str, template: str) -> str | None:
    """Номер версии из `version`: сам номер или полный вид «<пак>/<шаблон>/<версия>» (путь внутри каталога версии),
    как ждут остальные тулы; версия другого шаблона это ошибка аргумента."""
    raw = (optional_text(args, "version") or "").strip("/")
    if not raw:
        return None
    if "/" not in raw:
        return raw
    ref = version_arg(args)
    if (ref.pack, ref.template) != (pack, template):
        raise ArgumentError(
            localized_error(
                f"version: это версия шаблона {ref.pack}/{ref.template}, а template это {pack}/{template}",
                f"version: this is a version of {ref.pack}/{ref.template}, but template is {pack}/{template}",
            )
        )
    return ref.version


def _cell(cell: Mapping[str, Any]) -> str:
    mark = "*" if cell.get("changed") else ""
    return f"{_CELL.get(cell['status'], cell['status'])}{mark}:{cell['count']}"


def _status(lang: str, status: str) -> str:
    return (_STATUS_RU if lang == "ru" else _STATUS_EN).get(status, status)


def _localized_arg(raw: object, key: str) -> dict[str, str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return {"ru": raw, "en": raw}
    if isinstance(raw, Mapping) and raw and all(isinstance(v, str) for v in raw.values()):
        return {str(k): str(v) for k, v in raw.items()}
    raise ArgumentError(
        localized_error(f"{key}: строка или объект {{ru, en}}", f"{key}: a string or an object {{ru, en}} is expected")
    )


def _entry_json(entry: ScenarioEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "path": entry.path,
        "etag": entry.etag,
        "scenario": to_json(entry.scenario) if entry.scenario is not None else None,
        "error": entry.error,
    }


def _scenario_line(item: Mapping[str, Any], lang: str) -> str:
    body = item["scenario"]
    if body is None:
        return f"  {item['id']}: не читается: {item['error']}"
    inputs = ", ".join(f"{k}={v}" for k, v in body["inputs"].items())
    versions = f", versions {','.join(body['versions'])}" if body["versions"] else ""
    return (
        f'  {item["id"]} "{loc(body["name"], lang)}" [{inputs}] example {body.get("example") or "auto"}{versions}; '
        f"утверждений {len(body['assertions'])}, снимок {'есть' if body['snapshot'] else 'нет'}; etag {item['etag']}"
    )


class PackScenarioListTool(PackTool):
    spec = ToolSpec(
        name="pack_scenario_list",
        description=(
            "Студия шаблонов: сценарии шаблона (файлы <пак>/templates/<шаблон>/scenarios/<id>.yaml): имя, "
            "вводные, набор данных, версии, утверждения, снимок и etag для if_match. Битый файл виден с error. "
            "state: work_tree (по умолчанию), head или base."
        ),
        parameters=_schema(
            {"workspace_id": _WORKSPACE_ID, "template": _TEMPLATE, "state": _STATE, "format": FORMAT_PROP},
            ("workspace_id", "template"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        pack, template = template_arg(args)
        found = await (await self._deps.get(PackScenarioService)).list_scenarios(
            actor, uuid_arg(args, "workspace_id"), pack, template, _state_arg(args)
        )
        items = [_entry_json(e) for e in found.entries]
        lang = current_interface_language().value
        text = f"Сценариев {len(items)} в {found.dir}\n" + "\n".join(
            _scenario_line(i, lang) for i in items[:_MAX_LINES]
        )
        data = {"dir": found.dir, "scenarios": items}
        return layout_result(layout_arg(args), text, data)


class PackScenarioWriteTool(PackTool):
    spec = ToolSpec(
        name="pack_scenario_write",
        description=(
            "Студия шаблонов: создать или поправить сценарий (файл scenarios/<id>.yaml; id: строчная латиница, "
            "цифры, дефис). Без if_match сценария быть не должно (scenario_taken), с if_match (etag из "
            "pack_scenario_list) сценарий правится: названные поля заменяются, остальные остаются. Поля: name "
            "(строка или {ru, en}), description, example, inputs {id: значение}, versions, assertions (kind: "
            "document_state, document_count, meta_visible, participant_present, item_active, route_steps, "
            "route_pair (point, doc, slot, persona, present; optional true или false проверяет необязательность "
            "подписи, только при present true)), snapshot (не нужен: см. record_snapshot). record_snapshot: "
            "work_tree, head или base: "
            "«принять снимок»: текущий результат сценария пишется в snapshot, и прогон сверяет с ним. Не требует "
            "права на выпущенные версии: сценарии лежат вне каталога версии. Результаты считает "
            "pack_scenario_run."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "template": _TEMPLATE,
                "id": {"type": "string", "description": "Id сценария (имя файла без .yaml)"},
                "name": {"type": ["string", "object"]},
                "description": {"type": ["string", "object"]},
                "example": {"type": "string"},
                "inputs": {"type": "object"},
                "versions": {"type": "array", "items": {"type": "string"}},
                "assertions": {"type": "array", "items": {"type": "object"}},
                "record_snapshot": {"type": "string", "enum": ["work_tree", "head", "base"]},
                "version": _version_prop("Версия для снимка, если сценарий не привязан к одной"),
                "if_match": {"type": "string", "description": "Etag файла сценария: правка существующего"},
                "format": FORMAT_PROP,
            },
            ("workspace_id", "template", "id"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:  # noqa: C901 — разбор аргументов и сборка вида
        pack, template = template_arg(args)
        workspace_id = uuid_arg(args, "workspace_id")
        scenario_id = text_arg(args, "id")
        if_match = etag_arg(args)
        service = await self._deps.get(PackScenarioService)
        body: dict[str, Any] = {
            "format": 1,
            "name": {},
            "description": {},
            "inputs": {},
            "versions": [],
            "assertions": [],
        }
        if if_match is not None:
            listing = await service.list_scenarios(actor, workspace_id, pack, template, "work_tree")
            current = next((e for e in listing.entries if e.id == scenario_id), None)
            if current is None:
                raise PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id)
            if current.scenario is not None:
                body = dict(to_json(current.scenario))
        for key in ("name", "description"):
            value = _localized_arg(args.get(key), key)
            if value is not None:
                body[key] = value
        if "inputs" in args:
            body["inputs"] = _inputs_arg(args)
        for key in ("example", "versions", "assertions"):
            if key in args:
                body[key] = args[key]
        if not body["name"]:
            raise ArgumentError(localized_error("укажите name сценария", "specify the scenario name"))
        snap = optional_text(args, "record_snapshot")
        entry = await service.put(
            actor,
            workspace_id,
            pack,
            template,
            scenario_id,
            body,
            if_match=if_match,
            record_snapshot=_state_arg({"state": snap}) if snap else None,
            version=_version_number(args, pack, template),
        )
        data = _entry_json(entry)
        lang = current_interface_language().value
        head = ("Сценарий поправлен." if if_match else "Сценарий создан.") + (" Снимок принят." if snap else "")
        text = head + "\n" + _scenario_line(data, lang)
        return layout_result(layout_arg(args), text, data)


class PackScenarioDeleteTool(PackTool):
    spec = ToolSpec(
        name="pack_scenario_delete",
        description=(
            "Студия шаблонов: удалить сценарий (мягко: файл остаётся в истории git). Ответ содержит тело удалённого "
            "сценария (scenario) и его вернуть можно pack_scenario_write с этими полями без if_match. if_match "
            "(etag) защищает от удаления чужой правки (stale_file)."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "template": _TEMPLATE,
                "id": {"type": "string"},
                "if_match": {"type": "string"},
                "format": FORMAT_PROP,
            },
            ("workspace_id", "template", "id"),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        pack, template = template_arg(args)
        workspace_id = uuid_arg(args, "workspace_id")
        scenario_id = text_arg(args, "id")
        service = await self._deps.get(PackScenarioService)
        listing = await service.list_scenarios(actor, workspace_id, pack, template, "work_tree")
        found = next((e for e in listing.entries if e.id == scenario_id), None)
        if found is None:
            raise PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id)
        await service.delete(actor, workspace_id, pack, template, scenario_id, if_match=etag_arg(args))
        data = {
            "deleted": True,
            **_entry_json(found),
            "restore": localized_error(
                "Вернуть: pack_scenario_write с полями из scenario без if_match.",
                "Restore: pack_scenario_write with the fields from scenario and no if_match.",
            ),
        }
        return layout_result(layout_arg(args), f"Сценарий {scenario_id} удалён. " + str(data["restore"]), data)


def _run_text(body: Mapping[str, Any], lang: str) -> str:
    cov = body["coverage"]
    lines = [
        (
            f"Прогон {body['pack']}/{body['template']}/{body['version']} [{body['state']}]: "
            f"{_status(lang, 'passed')} {body['passed']}, {_status(lang, 'failed')} {body['failed']}, "
            f"{_status(lang, 'error')} {body['errors']}, {_status(lang, 'unchecked')} {body['unchecked']}"
        ),
    ]
    for item in body["results"][:_MAX_LINES]:
        lines.append(
            f"  {item['scenario']}: {_status(lang, item['status'])}"
            + (f" ({item['message']})" if item.get("message") else "")
        )
        lines += [
            f"    ожидалось {fail['expected']}, получено {fail['actual']} [{fail['kind']}]"
            for fail in item["failures"][:3]
        ]
        lines += [f"    {change['symbol']} {change['section']} {change['id']}" for change in item["changes"][:3]]
    lines.append(
        f"Покрытие правил: {cov['rules_covered']} из {cov['rules_total']} (половинчато {cov['rules_half']}, "
        f"не покрыто {cov['rules_uncovered']}), сценариев {cov['scenarios']}"
    )
    return "\n".join(lines)


class PackScenarioRunTool(PackTool):
    spec = ToolSpec(
        name="pack_scenario_run",
        description=(
            "Студия шаблонов: прогнать сценарии шаблона (все или scenarios) на версии и сверить результат с "
            "утверждениями и снимком: статус каждого: passed (совпало), failed (изменилось: что ожидалось и что "
            "получено), error (вводные не подходят версии), unchecked (вне versions сценария); и покрытие "
            "правил (сколько правил манифеста сценарии проверяют). state: work_tree (по умолчанию), head или "
            "base. Только чтение; не чаще 20 в секунду на человека."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "template": _TEMPLATE,
                "scenarios": {"type": "array", "items": {"type": "string"}, "description": "Id сценариев; все"},
                "state": _STATE,
                "version": _version_prop("Версия, по умолчанию новейшая"),
                "format": FORMAT_PROP,
            },
            ("workspace_id", "template"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        pack, template = template_arg(args)
        raw = args.get("scenarios")
        if raw is not None and not (isinstance(raw, list) and all(isinstance(i, str) for i in raw)):
            raise ArgumentError(localized_error("scenarios: список id", "scenarios: a list of ids is expected"))
        service = await self._deps.get(PackScenarioService)
        try:
            reply = await service.run(
                actor,
                uuid_arg(args, "workspace_id"),
                pack,
                template,
                state=_state_arg(args),
                scenarios=list(raw) if isinstance(raw, list) else None,
                version=_version_number(args, pack, template),
            )
        except PackStudioError as exc:
            return refusal(exc, hint=outcome_hint(exc))
        body = reply.body
        if body is None:
            raise ArgumentError("empty reply")
        lang = current_interface_language().value
        return layout_result(layout_arg(args), _run_text(body, lang), body)


def _digest_line(digest: Mapping[str, Any]) -> str:
    docs = [f"{k}" for k, v in digest["documents"].items() if v == "active"]
    points = [f"{p['id']}({len(p['items'])} п., {len(p['steps'])} ш., {p['pairs']} пар)" for p in digest["points"]]
    people = ", ".join(digest["participants"]) or "-"
    return f"документы: {', '.join(docs) or '-'}; участники: {people}; точки: {', '.join(points) or '-'}"


class PackOutcomeAtlasTool(PackTool):
    spec = ToolSpec(
        name="pack_outcome_atlas",
        description=(
            "Студия шаблонов: атлас результата: какие вводные (измерения) вообще меняют результат версии и сколько "
            "различных исходов получается. Ответ: измерения (вводная, число значений, какие разделы меняет), "
            "игнорируемые вводные, число комбинаций, строк и исходов и группы исходов (сколько строк в каждой, что "
            "в комплекте, примеры комбинаций). pin {вводная: значение} фиксирует вводные и сужает таблицу. limit: "
            "сколько групп показать (10, до 50). rows: N добавляет N строк «комбинация, исход». Слишком большая "
            "таблица: atlas_too_large, закрепите вводные. Только чтение; не чаще 6 в минуту."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "state": _STATE,
                "scenario": _SCENARIO,
                "example": {"type": "string"},
                "pin": {"type": "object", "description": 'Закрепление вводных {"kind": "research"}'},
                "limit": {"type": "integer", "default": 10},
                "rows": {"type": "integer", "default": 0},
                "format": FORMAT_PROP,
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:  # noqa: C901 — разбор аргументов и сборка вида
        ref = version_arg(args)
        pins = _inputs_arg({"inputs": args.get("pin")})
        service = await self._deps.get(PackAtlasService)
        try:
            reply = await service.atlas(
                actor,
                uuid_arg(args, "workspace_id"),
                ref.pack,
                ref.template,
                ref.version,
                _state_arg(args),
                example=optional_text(args, "example"),
                scenario=optional_text(args, "scenario"),
                pins=pins,
            )
        except PackStudioError as exc:
            return refusal(exc, hint=_atlas_hint(exc))
        body = reply.body
        if body is None:
            raise ArgumentError("empty reply")
        limit = int_arg(args, "limit", 10, lo=1, hi=_MAX_GROUPS)
        row_n = int_arg(args, "rows", 0, lo=0, hi=_MAX_ROWS)
        names = [d["input"] for d in body["dimensions"]]
        groups = sorted(body["outcomes"], key=lambda o: -o["rows"])
        examples: dict[str, list[str]] = {}
        for row in body["rows"]:
            bucket = examples.setdefault(row["outcome"], [])
            if len(bucket) < 2:  # noqa: PLR2004
                bucket.append(" ".join(f"{n}={v}" for n, v in zip(names, decode_key(row["key"]), strict=False)))
        lines = [
            (
                f"{body['pack']}/{body['template']}/{body['version']} [{body['state']}]: измерений {len(names)}, "
                f"комбинаций {body['combinations_total']}, строк {body['rows_total']}, "
                f"исходов {body['outcomes_distinct']}"
            ),
            "Измерения:",
        ]
        lines += [
            f"  {d['input']} ({len(d['values'])} знач., умолч. {d['default']}) меняет {', '.join(d['affects'])}"
            for d in body["dimensions"][:_MAX_LINES]
        ]
        if body["ignored"]:
            lines.append("Не влияют: " + ", ".join(f"{i['input']} ({i['reason']})" for i in body["ignored"][:20]))
        lines.append(f"Группы исходов (по числу строк, показано {min(limit, len(groups))} из {len(groups)}):")
        for g in groups[:limit]:
            lines.append(f"  {g['id']} строк {g['rows']}: {_digest_line(g['digest'])}")
            lines += [f"    например {e}" for e in examples.get(g["id"], [])]
        shown_rows = body["rows"][:row_n]
        if shown_rows:
            lines.append("Строки:")
            lines += [
                f"  {' '.join(f'{n}={v}' for n, v in zip(names, decode_key(r['key']), strict=False))} -> {r['outcome']}"
                for r in shown_rows
            ]
        data = {
            **{k: body[k] for k in ("dimensions", "ignored", "combinations_total", "rows_total", "outcomes_distinct")},
            "outcomes": [
                {"id": g["id"], "rows": g["rows"], "digest": g["digest"], "examples": examples.get(g["id"], [])}
                for g in groups[:limit]
            ],
            "rows": shown_rows,
        }
        return layout_result(layout_arg(args), "\n".join(lines), data)


def _atlas_hint(exc: PackStudioError) -> str | None:
    if exc.code is PackStudioErrorCode.atlas_too_large:
        return localized_error(
            "Таблица слишком велика: закрепите часть вводных аргументом pin (список даёт pack_outcome_inputs).",
            "The table is too large: pin some inputs with the pin argument (pack_outcome_inputs lists them).",
        )
    return outcome_hint(exc)


class PackOutcomeExplainTool(PackTool):
    spec = ToolSpec(
        name="pack_outcome_explain",
        description=(
            "Студия шаблонов: «Почему?» элемента результата: цепочка решений от условий до исхода (правило, где "
            "оно в манифесте, условие, факты, held или not_held), другие элементы с теми же правилами и «что "
            "если»: что станет с элементом, если одну вводную поставить в другое значение. element: "
            '{"section": "documents", "id": "<id>"}; разделы documents, meta, forms, participants, points, '
            "route, checks (id из pack_outcome; вложенные через «/»: <точка>/<документ>). Вводные как у "
            "pack_outcome. Элемента нет: outcome_element_not_found. Только чтение; не чаще 20 в секунду."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "element": {
                    "type": "object",
                    "properties": {"section": {"type": "string", "enum": list(_SECTIONS)}, "id": {"type": "string"}},
                    "required": ["section", "id"],
                },
                "state": _STATE,
                "scenario": _SCENARIO,
                "example": {"type": "string"},
                "inputs": {"type": "object"},
                "format": FORMAT_PROP,
            },
            ("workspace_id", "version", "element"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:  # noqa: C901 — разбор аргументов и сборка вида
        ref = version_arg(args)
        raw = args.get("element")
        if not isinstance(raw, Mapping) or raw.get("section") not in _SECTIONS or not str(raw.get("id") or "").strip():
            raise ArgumentError(
                localized_error(
                    'element: {"section": <раздел>, "id": <id>}',
                    'element: {"section": <section>, "id": <id>} is expected',
                )
            )
        element = ElementRef(raw["section"], str(raw["id"]).strip())
        request = ExplainRequest(
            element=element,
            state=_state_arg(args),
            scenario=optional_text(args, "scenario"),
            example=optional_text(args, "example"),
            inputs=_inputs_arg(args),
        )
        service = await self._deps.get(PackOutcomeService)
        try:
            reply = await service.explain(
                actor, uuid_arg(args, "workspace_id"), ref.pack, ref.template, ref.version, request
            )
        except PackStudioError as exc:
            return refusal(exc, hint=outcome_hint(exc))
        body = reply.body
        if body is None:
            raise ArgumentError("empty reply")
        lines = [f"{element.section}:{element.id} [{body['state']}]", "Цепочка решений:"]
        for step in body["chain"][:_MAX_LINES]:
            rule = step["rule"]
            where = (
                f"{rule['file']}#{rule['pointer']}" if rule["origin"] == "manifest" else f"builtin:{rule['builtin']}"
            )
            lines.append(f"  {step['status']} {step['effect']} {step['kind']}: {condition_of(step)} | {where}")
        if not body["chain"]:
            lines.append("  (решений нет: элемент безусловный)")
        readers = body["readers"]
        if readers:
            lines.append(
                f"Те же правила решают ещё {len(readers)} элементов: "
                + ", ".join(f"{r['section']}:{r['id']}" for r in readers[:10])
            )
        if body["counterfactuals"]:
            lines.append("Что если:")
            lines += [f"  {c['input']}={c['value']} -> {c['result']}" for c in body["counterfactuals"][:_MAX_LINES]]
        return layout_result(layout_arg(args), "\n".join(lines), body)


class PackOutcomeMatrixTool(PackTool):
    spec = ToolSpec(
        name="pack_outcome_matrix",
        description=(
            "Студия шаблонов: матрица «сценарии на разделы» результата: у каждой клетки статус ok (ожидание "
            "сценария выполнено), chg (не выполнено или раздел отличается от базы), -- (ожидания нет), err "
            "(результата нет: вводные не подходят) и число элементов. against: base подсвечивает раздел, "
            "изменённый против базовой ветки. scenarios: список id (все). Только чтение; не чаще 6 в минуту."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "state": _STATE,
                "scenarios": {"type": "array", "items": {"type": "string"}},
                "against": {"type": "string", "enum": ["base"]},
                "format": FORMAT_PROP,
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        raw = args.get("scenarios")
        if raw is not None and not (isinstance(raw, list) and all(isinstance(i, str) for i in raw)):
            raise ArgumentError(localized_error("scenarios: список id", "scenarios: a list of ids is expected"))
        against = optional_text(args, "against")
        if against not in {None, "base"}:
            raise ArgumentError(localized_error("against: base", "against: base"))
        service = await self._deps.get(PackCompareService)
        try:
            reply = await service.matrix(
                actor,
                uuid_arg(args, "workspace_id"),
                ref.pack,
                ref.template,
                ref.version,
                state=_state_arg(args),
                scenarios=list(raw) if isinstance(raw, list) else None,
                against="base" if against else None,
            )
        except PackStudioError as exc:
            return refusal(exc, hint=outcome_hint(exc))
        body = reply.body
        if body is None:
            raise ArgumentError("empty reply")
        cols = body["columns"]
        lines = [f"{'сценарий':<24} " + " ".join(f"{c[:9]:<9}" for c in cols)]
        for row in body["rows"][:_MAX_LINES]:
            cells = " ".join(f"{_cell(c):<9}" for c in row["cells"])
            lines.append(
                f"{row['scenario'][:24]:<24} {cells}" + (f"  ({row['message']})" if row.get("message") else "")
            )
        lines.append("* раздел отличается от базы")
        return layout_result(layout_arg(args), "\n".join(lines), body)
