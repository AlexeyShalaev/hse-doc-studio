"""Вид сравнений результата для агента (MCP `pack_outcome_compare` и `pack_outcome_impact`, template-studio-outcome.md,
4.5 и 4.7, срез O7).

Чистые функции над словарями ответов `PackOutcomeCompare` и `PackOutcomeImpact` (те же, что отдают эндпоинты): ввода-
вывода нет. Агент без лишних токенов узнаёт «что изменится» и «в скольких сценариях»: сводка, изменения со знаками
`+`, `~`, `-` по разделам и причина каждого изменения из трассы (правило, исход слева и справа, факты).

- `compact` (по умолчанию): у изменения одна главная причина, у сценария не больше `MAX_CHANGES` изменений.
- `full`: все причины изменения (до шести), все изменения.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from hse_doc_studio.use_cases.mcp.tools.pack_outcome_view import loc

Detail = Literal["compact", "full"]

MAX_CHANGES: Final = 12
_MAX_REASONS_COMPACT = 1
_MAX_REASONS_FULL = 6

_TEXT: Final[dict[str, dict[str, str]]] = {
    "ru": {
        "compare": "Сравнение {ref}",
        "side": "  {name}: {state}{scenario}{example}",
        "inputs_diff": "Вводные различаются: {items}",
        "inputs_same": "Вводные одинаковы",
        "identical": "Результаты совпадают: изменений нет.",
        "differ": "Результаты различаются: {summary}",
        "section_line": "{section} ({counts})",
        "no_reason": "причина в соседних элементах",
        "more": "  и ещё {n} изменений (detail: full покажет все)",
        "impact": "До и после {ref}: {base} -> work_tree",
        "impact_head": "Изменится результат в {changed} из {total} сценариев "
        "(без изменений {unchanged}, ошибок {errors})",
        "impact_none": "У шаблона нет сценариев для этой версии: сравнивать нечего.",
        "impact_sections": "Разделы: {summary}",
        "impact_atlas": "Атлас: изменилось {changed} из {rows} строк, исходов было {before}, стало {after}.",
        "impact_atlas_none": "Атлас: не считался (include_atlas выключен или таблица шире предела).",
        "scenario_changed": "{id}: изменился",
        "scenario_unchanged": "{id}: без изменений",
        "scenario_error": "{id}: ОШИБКА: {message}",
        "findings": "Новые находки линтера результата: {n}",
        "revision": "Ревизии: {base} -> {work_tree}",
    },
    "en": {
        "compare": "Compare {ref}",
        "side": "  {name}: {state}{scenario}{example}",
        "inputs_diff": "Inputs differ: {items}",
        "inputs_same": "The inputs are the same",
        "identical": "The outcomes are identical: no changes.",
        "differ": "The outcomes differ: {summary}",
        "section_line": "{section} ({counts})",
        "no_reason": "the reason is in neighbouring elements",
        "more": "  and {n} more changes (detail: full shows all)",
        "impact": "Before and after {ref}: {base} -> work_tree",
        "impact_head": "The outcome changes in {changed} of {total} scenarios ({unchanged} unchanged, {errors} errors)",
        "impact_none": "The template has no scenarios for this version: nothing to compare.",
        "impact_sections": "Sections: {summary}",
        "impact_atlas": "Atlas: {changed} of {rows} rows changed, outcomes {before} -> {after}.",
        "impact_atlas_none": "Atlas: not calculated (include_atlas is off or the table is wider than the limit).",
        "scenario_changed": "{id}: changed",
        "scenario_unchanged": "{id}: unchanged",
        "scenario_error": "{id}: ERROR: {message}",
        "findings": "New outcome lint findings: {n}",
        "revision": "Revisions: {base} -> {work_tree}",
    },
}


def tr(lang: str, key: str, **kw: object) -> str:
    return _TEXT["en" if lang == "en" else "ru"][key].format(**kw)


@dataclass(frozen=True, slots=True)
class CompareOptions:
    detail: Detail = "compact"
    lang: str = "ru"
    # Показать только эти разделы; пусто: все.
    sections: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompareView:
    text: str
    data: dict[str, Any]
    truncated: bool = False


def _term(term: Mapping[str, Any]) -> str:
    expected = ", ".join(map(str, term.get("expected") or ()))
    return {
        "in": f"{term['subject']} in [{expected}]",
        "equals": f"{term['subject']} = {expected}",
        "contains_any": f"{term['subject']} contains any of [{expected}]",
        "present": f"{term['subject']} is present",
        "truthy": f"{term['subject']} is on",
    }.get(term["op"], f"{term['subject']} {term['op']} {expected}")


def _facts(actual: Mapping[str, str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in actual.items())


def _reason_line(reason: Mapping[str, Any]) -> str:
    rule = reason["rule"]
    where = f"{rule['file']}#{rule['pointer']}" if rule["origin"] == "manifest" else f"builtin:{rule['builtin']}"
    cond = " and ".join(_term(t) for t in reason.get("terms") or ())
    before, after = reason.get("before") or "-", reason.get("after") or "-"
    facts_before, facts_after = _facts(reason.get("before_actual") or {}), _facts(reason.get("after_actual") or {})
    facts = f"{facts_before} -> {facts_after}" if facts_before != facts_after else facts_after
    suffix = f" ({facts})" if facts else ""
    return f"{reason['kind']}: {cond}: {before} -> {after}{suffix} | {where}"


def _change_lines(change: Mapping[str, Any], opts: CompareOptions, indent: str) -> list[str]:
    line = f"{indent}{change['symbol']} {change['label']}"
    before, after = change.get("before"), change.get("after")
    if before is not None or after is not None:
        line += f": {before if before is not None else '-'} -> {after if after is not None else '-'}"
    lines = [line]
    limit = _MAX_REASONS_FULL if opts.detail == "full" else _MAX_REASONS_COMPACT
    lines.extend(f"{indent}    why: {_reason_line(r)}" for r in (change.get("why") or [])[:limit])
    return lines


def _counts(delta: Mapping[str, Any]) -> str:
    return f"+{delta['added']} ~{delta['changed']} -{delta['removed']}"


def _summary_text(summary: Sequence[Mapping[str, Any]]) -> str:
    return "; ".join(f"{d['section']} {_counts(d)}" for d in summary)


def _grouped(changes: Sequence[Mapping[str, Any]], sections: Sequence[str]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for change in changes:
        if sections and change["section"] not in sections:
            continue
        groups.setdefault(change["section"], []).append(change)
    return groups


def _trim(change: Mapping[str, Any], opts: CompareOptions) -> dict[str, Any]:
    """Изменение для структурного вида: в `compact` причины урезаны до главной, в `full` как в ответе."""
    limit = _MAX_REASONS_FULL if opts.detail == "full" else _MAX_REASONS_COMPACT
    return {**change, "why": list(change.get("why") or [])[:limit]}


def _side_line(name: str, side: Mapping[str, Any], subject: Mapping[str, Any], lang: str) -> str:
    scenario = f", scenario {subject['scenario']}" if subject.get("scenario") else ""
    example = f", example {subject['example']}" if subject.get("example") else ""
    return tr(lang, "side", name=name, state=side["state"], scenario=scenario, example=example)


def _inputs_diff(left: Mapping[str, str], right: Mapping[str, str]) -> str:
    keys = [k for k in dict.fromkeys([*left, *right]) if left.get(k) != right.get(k)]
    return ", ".join(f"{k}: {left.get(k, '-')} -> {right.get(k, '-')}" for k in keys)


def compare_view(
    body: Mapping[str, Any], opts: CompareOptions, subjects: tuple[Mapping[str, Any], Mapping[str, Any]]
) -> CompareView:
    """Вид ответа `compare`. `subjects` это стороны запроса (сценарий и набор данных не повторены в ответе)."""
    lang = opts.lang
    ref = f"{body['pack']}/{body['template']}/{body['version']}"
    lines = [tr(lang, "compare", ref=ref)]
    lines.append(_side_line("left", body["left"], subjects[0], lang))
    lines.append(_side_line("right", body["right"], subjects[1], lang))
    diff = _inputs_diff(body["left"]["inputs"], body["right"]["inputs"])
    lines.append(tr(lang, "inputs_diff", items=diff) if diff else tr(lang, "inputs_same"))
    truncated = False
    if body["identical"]:
        lines.append(tr(lang, "identical"))
    else:
        lines.append(tr(lang, "differ", summary=_summary_text(body["summary"])))
        for section, changes in _grouped(body["changes"], opts.sections).items():
            delta = next((d for d in body["summary"] if d["section"] == section), None)
            counts = _counts(delta) if delta else ""
            lines.append(tr(lang, "section_line", section=section, counts=counts))
            shown = changes if opts.detail == "full" else changes[:MAX_CHANGES]
            for change in shown:
                lines.extend(_change_lines(change, opts, "  "))
            if len(shown) < len(changes):
                truncated = True
                lines.append(tr(lang, "more", n=len(changes) - len(shown)))
    data = {
        "version": ref,
        "left": body["left"],
        "right": body["right"],
        "identical": body["identical"],
        "summary": body["summary"],
        "changes": [_trim(c, opts) for c in body["changes"] if not opts.sections or c["section"] in opts.sections],
    }
    return CompareView("\n".join(lines), data, truncated)


def _impact_header(body: Mapping[str, Any], lang: str) -> list[str]:
    ref = f"{body['pack']}/{body['template']}/{body['version']}"
    summary = body["summary"]
    lines = [
        tr(lang, "impact", ref=ref, base=body["base"]),
        tr(lang, "revision", base=str(body["base_revision"])[:19], work_tree=str(body["work_tree_revision"])[:19]),
    ]
    if summary["scenarios_total"] == 0:
        lines.append(tr(lang, "impact_none"))
    else:
        lines.append(
            tr(
                lang,
                "impact_head",
                changed=summary["scenarios_changed"],
                total=summary["scenarios_total"],
                unchanged=summary["scenarios_unchanged"],
                errors=summary["scenarios_error"],
            )
        )
    if summary["sections"]:
        lines.append(tr(lang, "impact_sections", summary=_summary_text(summary["sections"])))
    atlas = summary.get("atlas")
    if atlas is None:
        lines.append(tr(lang, "impact_atlas_none"))
    else:
        lines.append(
            tr(
                lang,
                "impact_atlas",
                changed=atlas["rows_changed"],
                rows=atlas["rows_total"],
                before=atlas["outcomes_before"],
                after=atlas["outcomes_after"],
            )
        )
    if body["new_findings"]:
        lines.append(tr(lang, "findings", n=len(body["new_findings"])))
    return lines


def _impact_scenario(scenario: Mapping[str, Any], opts: CompareOptions) -> tuple[list[str], bool]:
    """Строки одного сценария «до и после» и признак, что изменения урезаны."""
    lang, scenario_id = opts.lang, scenario["scenario"]
    if scenario["status"] == "error":
        return [tr(lang, "scenario_error", id=scenario_id, message=scenario["message"])], False
    if scenario["status"] == "unchanged":
        return [tr(lang, "scenario_unchanged", id=scenario_id)], False
    lines = [tr(lang, "scenario_changed", id=scenario_id)]
    changes = [c for c in scenario["changes"] if not opts.sections or c["section"] in opts.sections]
    shown = changes if opts.detail == "full" else changes[:MAX_CHANGES]
    for change in shown:
        lines.extend(_change_lines(change, opts, "  "))
    cut = len(shown) < len(changes)
    if cut:
        lines.append(tr(lang, "more", n=len(changes) - len(shown)))
    return lines, cut


def impact_view(body: Mapping[str, Any], opts: CompareOptions) -> CompareView:
    """Вид ответа `impact`: «изменится N из M сценариев», разделы, атлас, сценарии с изменениями."""
    lang = opts.lang
    lines = _impact_header(body, lang)
    truncated = False
    for scenario in body["scenarios"]:
        scenario_lines, cut = _impact_scenario(scenario, opts)
        lines.extend(scenario_lines)
        truncated = truncated or cut
    data = {
        "version": f"{body['pack']}/{body['template']}/{body['version']}",
        "base": body["base"],
        "base_revision": body["base_revision"],
        "work_tree_revision": body["work_tree_revision"],
        "summary": body["summary"],
        "scenarios": [
            {
                **{k: v for k, v in s.items() if k not in {"name", "changes"}},
                "name": loc(s["name"], lang),
                "changes": [_trim(c, opts) for c in s["changes"] if not opts.sections or c["section"] in opts.sections],
            }
            for s in body["scenarios"]
        ],
        "new_findings": body["new_findings"],
    }
    return CompareView("\n".join(lines), data, truncated)
