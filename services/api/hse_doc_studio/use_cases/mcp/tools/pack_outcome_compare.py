"""Сравнения результата версии шаблона через MCP: `pack_outcome_compare` и `pack_outcome_impact`
(template-studio-outcome.md, 4.5 и 4.7, срез O7).

Тулы зовут ту же службу `PackCompareService`, что эндпоинты `outcome/compare` и `outcome/impact`, с теми же проверками:
раздел включён, право «Автор шаблонов», область токена `packs` (`PackTool.handle`), пространство только своё. Частота:
`compare` под правилом `pack_outcome` (20 в секунду), `impact` под `pack_impact` (6 в минуту), как у маршрутов. Тулы
только читают: записи и побочных эффектов нет (R15 дизайна).

Ответ рассчитан на агента: по умолчанию компактный текст (сводка, изменения со знаками по разделам, у каждого главная
причина из трассы); подробный вид (`detail: full`), разделы (`sections`) и структурный JSON (`format`) просятся явно.
Вид собирает `pack_outcome_compare_view.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.model import SECTIONS
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, optional_text, uuid_arg
from hse_doc_studio.use_cases.mcp.tools.pack_outcome import (
    _SCENARIO,
    _STATES,
    _choice,
    _flag,
    _inputs_arg,
    _state_arg,
    outcome_hint,
)
from hse_doc_studio.use_cases.mcp.tools.pack_outcome_compare_view import CompareOptions, compare_view, impact_view
from hse_doc_studio.use_cases.mcp.tools.pack_outcome_view import dump
from hse_doc_studio.use_cases.mcp.tools.packs import _VERSION, _WORKSPACE_ID, PackTool, _schema, refusal, version_arg
from hse_doc_studio.use_cases.pack_studio.outcome_compare import PackCompareService, Subject

_SIDE_KEYS: Final = ("state", "scenario", "example", "inputs")
_MAX_SCENARIOS: Final = 200
_BASES: Final = ("base", "head")

_SIDE = {
    "type": "object",
    "description": (
        "Сторона сравнения: state (work_tree, head, base), scenario, example, inputs. Что не названо, берётся из "
        "одноимённого верхнеуровневого аргумента (state по умолчанию work_tree)"
    ),
    "properties": {
        "state": {"type": "string", "enum": list(_STATES)},
        "scenario": {"type": "string"},
        "example": {"type": "string"},
        "inputs": {"type": "object"},
    },
}
_SECTIONS_ARG = {
    "type": "array",
    "items": {"type": "string", "enum": list(SECTIONS)},
    "description": "Показать изменения только этих разделов; по умолчанию все",
}


def _object_arg(args: Mapping[str, object], key: str) -> Mapping[str, object]:
    raw = args.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error(f"{key}: ожидается объект", f"{key}: an object is expected"))
    unknown = [k for k in raw if k not in _SIDE_KEYS]
    if unknown:
        raise ArgumentError(
            localized_error(
                f"{key}: неизвестное поле {unknown[0]!r}; доступны {', '.join(_SIDE_KEYS)}",
                f"{key}: unknown field {unknown[0]!r}; available: {', '.join(_SIDE_KEYS)}",
            )
        )
    return raw


def _subject(args: Mapping[str, object], key: str) -> Subject:
    """Сторона сравнения: поля объекта `left` или `right` поверх верхнеуровневых `state`, `scenario`, `example`,
    `inputs`."""
    side = _object_arg(args, key)
    merged: dict[str, object] = {name: args[name] for name in _SIDE_KEYS if name in args}
    merged.update(side)
    # Вводные стороны поверх общих: объекты вводных складываются, а не заменяют друг друга.
    shared = _inputs_arg({"inputs": args.get("inputs")}) if args.get("inputs") is not None else {}
    own = _inputs_arg({"inputs": side.get("inputs")}) if side.get("inputs") is not None else {}
    return Subject(
        state=_state_arg(merged),
        scenario=optional_text(merged, "scenario"),
        example=optional_text(merged, "example"),
        inputs={**shared, **own},
    )


def _sections_arg(args: Mapping[str, object]) -> tuple[str, ...]:
    raw = args.get("sections")
    if raw is None:
        return ()
    items = raw.split(",") if isinstance(raw, str) else raw
    if not isinstance(items, list):
        raise ArgumentError(
            localized_error("sections: ожидается список разделов", "sections: a list of sections is expected")
        )
    names = [str(item).strip() for item in items if str(item).strip()]
    unknown = [name for name in names if name not in SECTIONS]
    if unknown:
        raise ArgumentError(
            localized_error(
                f"sections: неизвестный раздел {unknown[0]!r}; доступны {', '.join(SECTIONS)}",
                f"sections: unknown section {unknown[0]!r}; available: {', '.join(SECTIONS)}",
            )
        )
    return tuple(names)


def _scenarios_arg(args: Mapping[str, object]) -> list[str] | None:
    raw = args.get("scenarios")
    if raw is None:
        return None
    items = raw.split(",") if isinstance(raw, str) else raw
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise ArgumentError(
            localized_error("scenarios: ожидается список id", "scenarios: a list of scenario ids is expected")
        )
    names = [i.strip() for i in items if i.strip()]
    if len(names) > _MAX_SCENARIOS:
        raise ArgumentError(
            localized_error(
                f"scenarios: не больше {_MAX_SCENARIOS} сценариев", f"scenarios: at most {_MAX_SCENARIOS} scenarios"
            )
        )
    return names


def _subject_json(subject: Subject) -> dict[str, Any]:
    return {"scenario": subject.scenario, "example": subject.example}


def _result(view_text: str, data: Mapping[str, Any], layout: str, truncated: bool) -> ToolResult:
    if layout == "text":
        return ToolResult.ok(view_text, truncated=truncated)
    if layout == "json":
        return ToolResult.ok(dump(data), truncated=truncated)
    return ToolResult.ok(dump({"text": view_text, "data": data}), truncated=truncated)


class PackOutcomeCompareTool(PackTool):
    spec = ToolSpec(
        name="pack_outcome_compare",
        description=(
            "Студия шаблонов: сравнивает два результата версии шаблона без сборки PDF: что изменится между двумя "
            "наборами вводных, двумя сценариями или одной комбинацией на двух состояниях версии (work_tree против "
            "head или base: «что я наменял»). Ответ: изменения со знаками (+ появилось, ~ изменилось, - исчезло) по "
            "разделам (documents, meta, forms, participants, points, route, checks) и главная причина каждого "
            "изменения из трассы (правило, исход слева и справа, факты). Стороны left и right: "
            '{"state": "base", "scenario": "<id>", "inputs": {...}}; не названное берётся из верхнеуровневых '
            "state, scenario, example, inputs. Пример «до и после правки»: "
            '{"left": {"state": "base"}, "right": {"state": "work_tree"}, "inputs": {"supervisor": "company"}}. '
            "detail: compact (по умолчанию) или full (все причины и изменения). format: text, json или both. "
            "Только чтение."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "left": _SIDE,
                "right": _SIDE,
                "state": {"type": "string", "enum": list(_STATES), "default": "work_tree"},
                "scenario": _SCENARIO,
                "example": {"type": "string", "description": "Набор данных из pack_outcome_inputs"},
                "inputs": {"type": "object", "description": "Вводные для обеих сторон; сторона может переопределить"},
                "sections": _SECTIONS_ARG,
                "detail": {"type": "string", "enum": ["compact", "full"], "default": "compact"},
                "format": {"type": "string", "enum": ["text", "json", "both"], "default": "text"},
            },
            ("workspace_id", "version", "left", "right"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        left, right = _subject(args, "left"), _subject(args, "right")
        opts = CompareOptions(
            detail=_choice(args, "detail", ("compact", "full"), "compact"),  # type: ignore[arg-type]
            lang=current_interface_language().value,
            sections=_sections_arg(args),
        )
        layout = _choice(args, "format", ("text", "json", "both"), "text")
        service = await self._deps.get(PackCompareService)
        try:
            reply = await service.compare(
                actor, uuid_arg(args, "workspace_id"), ref.pack, ref.template, ref.version, left, right
            )
        except PackStudioError as exc:
            return refusal(exc, hint=outcome_hint(exc))
        if reply.body is None:  # без If-None-Match не бывает; защита от смены службы
            raise ArgumentError("empty reply")
        view = compare_view(reply.body, opts, (_subject_json(left), _subject_json(right)))
        return _result(view.text, view.data, layout, view.truncated)


class PackOutcomeImpactTool(PackTool):
    spec = ToolSpec(
        name="pack_outcome_impact",
        description=(
            "Студия шаблонов: «до и после» перед сохранением правки: считает сценарии шаблона на базе (вершина "
            "базовой ветки, base) или последнем коммите (head) и в рабочем дереве (с несохранёнными правками) и "
            "отвечает «изменится результат в N из M сценариев»: у каждого сценария статус (changed, unchanged, "
            "error: сценарий не читается на одной из сторон) и изменения со знаками + ~ - по разделам с причиной из "
            "трассы. include_atlas: true добавляет, у скольких строк атласа результат изменится (дольше, до "
            "нескольких секунд на ВКР). scenarios: список id (по умолчанию все). У пространства без git или без "
            "базовой ветки и у новой версии отвечает diff_base_unavailable с причиной. detail: compact (по "
            "умолчанию) или full. format: text, json или both. Только чтение."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "base": {"type": "string", "enum": list(_BASES), "default": "base"},
                "scenarios": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Id сценариев; все по умолчанию",
                },
                "include_atlas": {"type": "boolean", "default": False},
                "sections": _SECTIONS_ARG,
                "detail": {"type": "string", "enum": ["compact", "full"], "default": "compact"},
                "format": {"type": "string", "enum": ["text", "json", "both"], "default": "text"},
            },
            ("workspace_id", "version"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        base = _choice(args, "base", _BASES, "base")
        opts = CompareOptions(
            detail=_choice(args, "detail", ("compact", "full"), "compact"),  # type: ignore[arg-type]
            lang=current_interface_language().value,
            sections=_sections_arg(args),
        )
        layout = _choice(args, "format", ("text", "json", "both"), "text")
        service = await self._deps.get(PackCompareService)
        try:
            reply = await service.impact(
                actor,
                uuid_arg(args, "workspace_id"),
                ref.pack,
                ref.template,
                ref.version,
                base=base,  # type: ignore[arg-type]  # сужено _choice
                scenarios=_scenarios_arg(args),
                include_atlas=_flag(args, "include_atlas"),
            )
        except PackStudioError as exc:
            return refusal(exc, hint=_hint(exc))
        if reply.body is None:
            raise ArgumentError("empty reply")
        view = impact_view(reply.body, opts)
        return _result(view.text, view.data, layout, view.truncated)


def _hint(exc: PackStudioError) -> str | None:
    """Подсказка при отказе: как у результата, плюс предел размера ответа."""
    if exc.code is PackStudioErrorCode.outcome_too_large:
        return localized_error(
            "Ответ слишком большой: назовите меньше сценариев в scenarios или выберите разделы в sections.",
            "The response is too large: name fewer scenarios in scenarios or pick sections in sections.",
        )
    return outcome_hint(exc)
