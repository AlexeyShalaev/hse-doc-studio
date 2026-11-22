"""Результат версии шаблона через MCP: `pack_outcome_inputs`, `pack_outcome` (template-studio-outcome.md, 4.7, O3) и
`pack_outcome_lint` (линтер результата и покрытие правил сценариями, O8).

Тулы зовут ту же службу `PackOutcomeService`, что эндпоинты `outcome/inputs` и `outcome`, с теми же проверками:
раздел включён, право «Автор шаблонов», область токена `packs` (`PackTool.handle`), пространство только своё. Частота
`pack_outcome` (20 в секунду на человека) навешена правилом каталога, как у маршрутов. Тулы только читают: записи и
побочных эффектов нет (R15 дизайна).

Ответ рассчитан на агента: по умолчанию компактный текст (сводка, документы с итоговыми именами файлов, пункты,
шаги и пары маршрута, предупреждения); подробный вид (`detail: full`), разделы (`include`), трасса (`trace`) и
структурный JSON (`format`) просятся явно. Вид собирает `pack_outcome_view.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, json_result, optional_text, uuid_arg
from hse_doc_studio.use_cases.mcp.tools.pack_outcome_view import (
    DEFAULT_SECTIONS,
    EXPENSIVE,
    SECTIONS,
    ViewOptions,
    build_view,
    dump,
    loc,
    split_sections,
)
from hse_doc_studio.use_cases.mcp.tools.pack_plain import Naming, lint_plain_text, naming_of, plain_finding
from hse_doc_studio.use_cases.mcp.tools.packs import (
    _VERSION,
    _WORKSPACE_ID,
    PackTool,
    _schema,
    refusal,
    version_arg,
)
from hse_doc_studio.use_cases.pack_studio.outcome_lint import PackOutcomeLintService
from hse_doc_studio.use_cases.pack_studio.outcome_service import OutcomeRequest, OutcomeState, PackOutcomeService
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService

# Пределы вводных те же, что у запроса эндпоинта (`PackOutcomeRequest`): 64 ключа, значение до 128 знаков.
MAX_INPUTS: Final = 64
MAX_VALUE: Final = 128
_STATES: Final = ("work_tree", "head", "base")
_YES, _NO = "yes", "no"
_MAX_VALUES_LISTED: Final = 40

_SCENARIO = {
    "type": "string",
    "description": (
        "Сценарий шаблона (id файла scenarios/<id>.yaml): его вводные ложатся между умолчаниями и inputs, "
        "набор данных берётся у сценария (иначе auto:normal). Читается из того же state"
    ),
}

_STATE = {
    "type": "string",
    "enum": list(_STATES),
    "default": "work_tree",
    "description": (
        "Что читать: work_tree (рабочее дерево с несохранёнными правками), head (последний коммит ветки), "
        "base (вершина базовой ветки). head и base только у git-пространства"
    ),
}


def _state_arg(args: Mapping[str, object]) -> OutcomeState:
    raw = optional_text(args, "state") or "work_tree"
    if raw not in _STATES:
        raise ArgumentError(
            localized_error(
                f"state: ожидается одно из {', '.join(_STATES)}, получено {raw!r}",
                f"state: one of {', '.join(_STATES)} is expected, got {raw!r}",
            )
        )
    return raw  # type: ignore[return-value]  # сужено проверкой выше


def _input_value(key: object, value: object) -> str:
    if isinstance(value, bool):
        return _YES if value else _NO
    if not isinstance(value, str | int | float):
        raise ArgumentError(
            localized_error(
                f"inputs.{key}: ожидается строка, число или true и false",
                f"inputs.{key}: a string, a number or true and false is expected",
            )
        )
    text = str(value)
    if len(text) > MAX_VALUE:
        raise ArgumentError(
            localized_error(
                f"inputs.{key}: значение не длиннее {MAX_VALUE} знаков",
                f"inputs.{key}: the value is at most {MAX_VALUE} characters",
            )
        )
    return text


def _inputs_arg(args: Mapping[str, object]) -> dict[str, str]:
    """Вводные `{id: значение}`; логическое значение JSON это `yes` и `no`, число строка."""
    raw = args.get("inputs")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ArgumentError(
            localized_error('inputs: ожидается объект {"kind": "research", ...}', "inputs: an object is expected")
        )
    if len(raw) > MAX_INPUTS:
        raise ArgumentError(
            localized_error(f"inputs: не больше {MAX_INPUTS} вводных", f"inputs: at most {MAX_INPUTS} inputs")
        )
    return {str(key): _input_value(key, value) for key, value in raw.items()}


def _sections_arg(args: Mapping[str, object]) -> tuple[str, ...]:
    """`include`: список разделов, строка через запятую или `all`; по умолчанию комплект, люди, пункты, маршрут."""
    raw = args.get("include")
    if raw is None:
        return DEFAULT_SECTIONS
    items = raw.split(",") if isinstance(raw, str) else raw
    if not isinstance(items, list):
        raise ArgumentError(
            localized_error("include: ожидается список разделов", "include: a list of sections is expected")
        )
    names = [str(item).strip() for item in items if str(item).strip()]
    if "all" in names:
        return SECTIONS
    unknown = [name for name in names if name not in SECTIONS]
    if unknown:
        raise ArgumentError(
            localized_error(
                f"include: неизвестный раздел {unknown[0]!r}; доступны {', '.join(SECTIONS)} и all",
                f"include: unknown section {unknown[0]!r}; available: {', '.join(SECTIONS)} and all",
            )
        )
    return split_sections(names) or DEFAULT_SECTIONS


def _choice(args: Mapping[str, object], key: str, allowed: tuple[str, ...], default: str) -> str:
    raw = optional_text(args, key) or default
    if raw not in allowed:
        raise ArgumentError(
            localized_error(
                f"{key}: ожидается одно из {', '.join(allowed)}, получено {raw!r}",
                f"{key}: one of {', '.join(allowed)} is expected, got {raw!r}",
            )
        )
    return raw


def _flag(args: Mapping[str, object], key: str) -> bool:
    raw = args.get(key, False)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes"}
    return raw is True


def outcome_hint(exc: PackStudioError) -> str | None:
    """Что делать при отказе результата: следующий шаг для агента, а не только код."""
    code = exc.code
    if code is PackStudioErrorCode.inputs_invalid:
        field = exc.ctx.get("field")
        return localized_error(
            f"Допустимые вводные и значения ({field}) показывает pack_outcome_inputs; поправьте inputs или example.",
            f"pack_outcome_inputs lists the valid inputs and values ({field}); fix inputs or example.",
        )
    if code is PackStudioErrorCode.diff_base_unavailable:
        reason = exc.ctx.get("reason")
        return {
            "no_git": localized_error(
                "У пространства нет git, поэтому есть только state=work_tree.",
                "The workspace has no git, so only state=work_tree exists.",
            ),
            "no_base": localized_error(
                "У пространства нет базовой ветки: используйте state=work_tree или state=head.",
                "The workspace has no base branch: use state=work_tree or state=head.",
            ),
            "new_version": localized_error(
                "Версия новая: в этом состоянии её ещё нет, сравнивать не с чем. Считайте state=work_tree.",
                "The version is new: it does not exist in this state yet. Use state=work_tree.",
            ),
        }.get(str(reason))
    if code in {PackStudioErrorCode.scenario_not_found, PackStudioErrorCode.scenario_invalid}:
        return localized_error(
            "Сценарии шаблона лежат в <пак>/templates/<шаблон>/scenarios/<id>.yaml (id: строчная латиница, цифры, "
            "дефис); без аргумента scenario результат считается по умолчаниям и inputs.",
            "Template scenarios live in <pack>/templates/<template>/scenarios/<id>.yaml (id: lowercase Latin "
            "letters, digits, hyphens); without the scenario argument the outcome uses the defaults and inputs.",
        )
    if code is PackStudioErrorCode.outcome_busy:
        seconds = exc.ctx.get("retry_after_s")
        return localized_error(
            f"Расчёт занят или не уложился в срок: повторите через {seconds} с.",
            f"The calculation is busy or timed out: retry in {seconds} s.",
        )
    if code is PackStudioErrorCode.version_unreadable:
        return localized_error(
            "Манифест версии не читается: pack_lint покажет находки с файлом и строкой.",
            "The version manifest cannot be read: pack_lint shows findings with a file and a line.",
        )
    return None


class PackOutcomeInputsTool(PackTool):
    spec = ToolSpec(
        name="pack_outcome_inputs",
        description=(
            "Студия шаблонов: вводные версии для pack_outcome: id (lang, kind, staffing, supervisor, co_supervisor, "
            "academic_supervisor, nda, meta.<поле>, answer.<анкета>.<поле>, variant.<документ>), допустимые "
            "значения, значение по умолчанию, какие разделы результата вводная меняет (affects) и сколько правил её "
            "читают (rules); наборы данных (examples). Только чтение. Пример: "
            '{"workspace_id": "<uuid>", "version": "hse-cs-se/vkr/2026.1.2"}.'
        ),
        parameters=_schema(
            {"workspace_id": _WORKSPACE_ID, "version": _VERSION, "state": _STATE, "scenario": _SCENARIO},
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        state = _state_arg(args)
        service = await self._deps.get(PackOutcomeService)
        try:
            reply = await service.inputs(
                actor,
                uuid_arg(args, "workspace_id"),
                ref.pack,
                ref.template,
                ref.version,
                state,
                scenario=optional_text(args, "scenario"),
            )
        except PackStudioError as exc:
            return refusal(exc, hint=outcome_hint(exc))
        body = reply.body
        if body is None:  # без If-None-Match не бывает; защита от смены службы
            raise ArgumentError("empty reply")
        lang = current_interface_language().value
        inputs = []
        for item in body["inputs"]:
            values = [v["value"] for v in item["values"]]
            labels = {v["value"]: loc(v["label"], lang) for v in item["values"] if v.get("label")}
            entry: dict[str, object] = {
                "id": item["id"],
                "group": item["group"],
                "type": item["type"],
                "default": item["default"],
                "values": values[:_MAX_VALUES_LISTED],
                "affects": item["affects"],
                "rules": item["rules"],
            }
            if item.get("label"):
                entry["label"] = loc(item["label"], lang)
            if labels:
                entry["value_labels"] = dict(list(labels.items())[:_MAX_VALUES_LISTED])
            if len(values) > _MAX_VALUES_LISTED:
                entry["values_total"] = len(values)
            inputs.append(entry)
        examples = [{"id": e["id"], **({"error": e["error"]} if e.get("error") else {})} for e in body["examples"]]
        hint = localized_error(
            "Значения передавайте в pack_outcome аргументом inputs; не названные вводные берутся по умолчанию.",
            "Pass values to pack_outcome in inputs; inputs you do not name keep their defaults.",
        )
        return json_result(
            {
                "version": f"{body['pack']}/{body['template']}/{body['version']}",
                "state": body["state"],
                "revision": body["revision"],
                "default_example": body["default_example"],
                "examples": examples,
                "inputs": inputs,
                "hint": hint,
            }
        )


class PackOutcomeTool(PackTool):
    spec = ToolSpec(
        name="pack_outcome",
        description=(
            "Студия шаблонов: что получится у версии шаблона при заданных вводных, без сборки PDF: документы в "
            "комплекте с итоговыми именами файлов (и почему остальных нет), участники, пункты точек сдачи, шаги и пары "
            "подписей маршрута, предупреждения. Вводные inputs поверх умолчаний и сценария scenario (список в "
            "pack_outcome_inputs): "
            '{"kind": "research", "staffing": "team2", "nda": true}. state: work_tree (с несохранёнными '
            "правками, по умолчанию), head или base для сравнения «до» (читаются из git). include: нужные разделы "
            f"({', '.join(SECTIONS)}; all для всех), по умолчанию {', '.join(DEFAULT_SECTIONS)}; checks и branches "
            "считаются только по запросу. trace: true добавляет решения (правило, условие, факты), на которые "
            "ссылаются показанные элементы. detail: compact (по умолчанию, краткий текст) или full (поля, языки, "
            "подписи пунктов, условия пар). format: text (по умолчанию), json (структурный) или both. Только чтение."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "state": _STATE,
                "scenario": _SCENARIO,
                "example": {
                    "type": "string",
                    "description": "Набор данных из pack_outcome_inputs (по умолчанию первый)",
                },
                "inputs": {
                    "type": "object",
                    "description": 'Вводные {id: значение}, например {"kind": "research", "nda": true}',
                },
                "include": {
                    "type": "array",
                    "items": {"type": "string", "enum": [*SECTIONS, "all"]},
                    "description": f"Разделы ответа; по умолчанию {', '.join(DEFAULT_SECTIONS)}",
                },
                "detail": {"type": "string", "enum": ["compact", "full"], "default": "compact"},
                "trace": {"type": "boolean", "default": False, "description": "Добавить трассу решений"},
                "format": {"type": "string", "enum": ["text", "json", "both"], "default": "text"},
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        state = _state_arg(args)
        inputs = _inputs_arg(args)
        sections = _sections_arg(args)
        detail = _choice(args, "detail", ("compact", "full"), "compact")
        layout = _choice(args, "format", ("text", "json", "both"), "text")
        wanted = frozenset(name for name in sections if name in EXPENSIVE)
        request = OutcomeRequest(
            state=state,
            scenario=optional_text(args, "scenario"),
            example=optional_text(args, "example"),
            inputs=inputs,
            include=wanted,  # type: ignore[arg-type]  # checks и branches: имена из EXPENSIVE
        )
        service = await self._deps.get(PackOutcomeService)
        try:
            reply = await service.outcome(
                actor, uuid_arg(args, "workspace_id"), ref.pack, ref.template, ref.version, request
            )
        except PackStudioError as exc:
            return refusal(exc, hint=outcome_hint(exc))
        if reply.body is None:
            raise ArgumentError("empty reply")
        view = build_view(
            reply.body,
            ViewOptions(
                sections=sections,
                detail=detail,  # type: ignore[arg-type]
                trace=_flag(args, "trace"),
                lang=current_interface_language().value,
                requested=inputs,
            ),
        )
        if layout == "text":
            return ToolResult.ok(view.text, truncated=view.truncated)
        if layout == "json":
            return ToolResult.ok(dump(view.data), truncated=view.truncated)
        return ToolResult.ok(dump({"text": view.text, "data": view.data}), truncated=view.truncated)


_SEVERITIES: Final = ("error", "warning", "info")
_MAX_FINDINGS: Final = 40
_WORDINGS: Final = ("plain", "tech")
_MAX_UNCOVERED: Final = 8


def _finding_lines(item: Mapping[str, Any]) -> list[str]:
    where = f" {item['file']}" + (f":{item['line']}" if item.get("line") else "") if item.get("file") else ""
    pointer = f" ({item['pointer']})" if item.get("pointer") else ""
    lines = [f"- [{item['severity']}] {item['rule_id']}{where}{pointer}: {item['message']}"]
    if item.get("hint"):
        lines.append(f"    как исправить: {item['hint']}")
    if item.get("witnesses"):
        sample = ", ".join(f"{k}={v}" for k, v in item["witnesses"][0].items())
        lines.append(f"    комбинация: {sample}")
    return lines


def _coverage_lines(cover: Mapping[str, Any]) -> list[str]:
    summary = (
        f"Покрытие правил сценариями: {cover.get('percent', 0)}% исходов "
        f"(правил {cover['rules_total']}: полностью {cover['rules_covered']}, наполовину {cover['rules_half']}, "
        f"не покрыто {cover['rules_uncovered']}); сценариев {cover['scenarios']}, комбинаций затронуто "
        f"{cover.get('rows_touched', 0)} из {cover.get('rows_total', 0)}."
    )
    lines = [summary]
    if cover.get("approximate"):
        lines.append("  Атлас слишком большой: цифры приближённые (нижняя граница).")
    rows = cover.get("uncovered_rows") or []
    if rows:
        lines.append("Чем закрыть пробелы (комбинации по убыванию пользы):")
        for row in rows[:_MAX_UNCOVERED]:
            sample = ", ".join(f"{k}={v}" for k, v in row["inputs"].items())
            lines.append(f"  +{row['gain']} исходов: {sample}")
    return lines


def lint_text(body: Mapping[str, Any], severity: str, limit: int) -> tuple[str, bool]:
    """Текстовый вид ответа линтера: сводка, находки не мягче `severity` и покрытие; `True`, если находки обрезаны."""
    order = {name: index for index, name in enumerate(_SEVERITIES)}
    shown = [f for f in body["findings"] if order[f["severity"]] <= order[severity]]
    header = (
        f"Линтер результата {body['pack']}/{body['template']}/{body['version']} ({body['state']}): "
        f"ошибок {body['errors']}, предупреждений {body['warnings']}, информации {body.get('infos', 0)}."
    )
    lines = [header]
    if body.get("atlas_skipped"):
        lines.append("Таблица исходов слишком большая: только статические правила.")
    if body.get("jinja") == "unavailable":
        lines.append("Правила Jinja только на рабочем дереве (state=work_tree).")
    for item in shown[:limit]:
        lines.extend(_finding_lines(item))
    if not shown:
        lines.append("Находок нет.")
    lines.extend(_coverage_lines(body["coverage"]))
    return "\n".join(lines), len(shown) > limit


class PackOutcomeLintTool(PackTool):
    spec = ToolSpec(
        name="pack_outcome_lint",
        description=(
            "Студия шаблонов: линтер результата версии. Находит в манифесте слоты, которые не попадают в маршрут, "
            "шаги маршрута без человека, условия visible_if и when, которые не выполнятся никогда, обязательные, но "
            "скрытые поля, документы и пункты, которых не бывает, недостающие переводы, зашитые правила движка, не "
            "согласованные с манифестом, и (jinja: true, рабочее дерево) шаблоны Jinja, которые падают при рендере и "
            "молча копируются как есть. У каждой находки файл, указатель, строка и подсказка. Плюс покрытие правил "
            "пака сценариями (процент достижимых исходов, какие правила и комбинации ничего не проверяет, какие "
            "сценарии добавить). Слова по умолчанию те же, что на вкладке «Проверка» интерфейса (wording: plain: "
            "заголовок и «Как исправить», в квадратных скобках правило, файл и строка); wording: tech даёт тексты "
            "правил линтера. severity: error, warning (по умолчанию) или info. format: text (по умолчанию), "
            "json или both. Только чтение. Пример: "
            '{"workspace_id": "<uuid>", "version": "hse-cs-se/vkr/2026.1.2", "jinja": true}.'
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "state": _STATE,
                "jinja": {
                    "type": "boolean",
                    "default": False,
                    "description": "Добавить правила по файлам шаблонов (Jinja): дольше, только state=work_tree",
                },
                "severity": {"type": "string", "enum": list(_SEVERITIES), "default": "warning"},
                "limit": {"type": "integer", "default": _MAX_FINDINGS, "description": "Находок в тексте не больше"},
                "wording": {
                    "type": "string",
                    "enum": list(_WORDINGS),
                    "default": "plain",
                    "description": "plain: словами вкладки «Проверка» интерфейса; tech: тексты правил линтера",
                },
                "format": {"type": "string", "enum": ["text", "json", "both"], "default": "text"},
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:  # noqa: C901 — разбор аргументов и два вида
        ref = version_arg(args)
        state = _state_arg(args)
        wording = _choice(args, "wording", _WORDINGS, "plain")
        severity = _choice(args, "severity", _SEVERITIES, "warning")
        layout = _choice(args, "format", ("text", "json", "both"), "text")
        raw_limit = args.get("limit", _MAX_FINDINGS)
        limit = (
            raw_limit
            if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) and raw_limit > 0
            else _MAX_FINDINGS
        )
        service = await self._deps.get(PackOutcomeLintService)
        try:
            reply = await service.lint(
                actor,
                uuid_arg(args, "workspace_id"),
                ref.pack,
                ref.template,
                ref.version,
                state,
                jinja=_flag(args, "jinja"),
            )
        except PackStudioError as exc:
            return refusal(exc, hint=outcome_hint(exc))
        if reply.body is None:
            raise ArgumentError("empty reply")
        body: Mapping[str, Any] = reply.body
        if wording == "plain":
            naming = await self._naming(actor, args, state)
            text, truncated = lint_plain_text(body, naming, _SEVERITIES, severity, limit)
            body = {**body, "findings": [{**f, "plain": plain_finding(f, naming)} for f in body["findings"]]}
        else:
            text, truncated = lint_text(body, severity, limit)
        if layout == "text":
            return ToolResult.ok(text, truncated=truncated)
        if layout == "json":
            return ToolResult.ok(dump(body), truncated=False)
        return ToolResult.ok(dump({"text": text, "data": body}), truncated=truncated)

    async def _naming(self, actor: Actor, args: Mapping[str, object], state: OutcomeState) -> Naming:
        """Названия документов, подписей, точек сдачи и условий версии для слов интерфейса; чего нет, нейтрально."""
        ref = version_arg(args)
        workspace_id = uuid_arg(args, "workspace_id")
        desc = await (await self._deps.get(PackPreviewService)).describe(
            actor, workspace_id, ref.pack, ref.template, ref.version
        )
        inputs: list[Mapping[str, Any]] = []
        try:
            reply = await (await self._deps.get(PackOutcomeService)).inputs(
                actor, workspace_id, ref.pack, ref.template, ref.version, state
            )
            inputs = list((reply.body or {}).get("inputs") or [])
        except PackStudioError:
            inputs = []
        return naming_of(desc.version, inputs)
