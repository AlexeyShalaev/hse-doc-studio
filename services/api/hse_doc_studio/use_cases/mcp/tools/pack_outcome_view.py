"""Вид результата версии для агента (MCP `pack_outcome`, template-studio-outcome.md, 4.7, срез O3).

Чистые функции над словарём ответа `PackOutcome` (тот же, что отдаёт эндпоинт `outcome`): ввода-вывода нет. Цель:
агент без лишних токенов узнаёт «что получится при таких вводных».

- **Сводка** всегда: версия, состояние, вводные, число элементов по разделам, предупреждения.
- **Разделы** по `sections`: `compact` (по умолчанию) это строки текста с итоговыми именами файлов, пунктами, шагами и
  парами подписей; `full` добавляет поля, языки, подписи пунктов, условия пар, правила проверок.
- **Трасса** по `trace`: к элементам добавляются id решений, а в конце идут только те решения, на которые ссылаются
  показанные элементы (правило, условие, факты, исход). Без трассы `why` из структуры убирается.
- **Структурный вид** (`data`) повторяет те же разделы словарями: в `compact` урезанные, в `full` как в ответе.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

SECTIONS: Final = ("documents", "meta", "forms", "participants", "points", "route", "checks", "branches")
# Что отвечает на «что получится»: комплект, люди, пункты сдачи и маршрут; остальное по запросу.
DEFAULT_SECTIONS: Final = ("documents", "participants", "points", "route")
# Разделы, которые вычислитель считает только по `include` (дорогие части).
EXPENSIVE: Final = ("checks", "branches")

MAX_TRACE: Final = 200
_MAX_SUBJECTS = 6

Detail = Literal["compact", "full"]

_TEXT: Final[dict[str, dict[str, str]]] = {
    "ru": {
        "documents": "Документы: {n} в комплекте из {total}",
        "meta": "Поля проекта: {n} видимых из {total}",
        "meta_hidden": "  скрыты: {ids}",
        "forms": "Анкеты: {n} применимы из {total}",
        "form_fields": "{shown} полей видно, {required} обязательных",
        "form_off": "не применяется",
        "participants": "Участники: {n}",
        "absent": "  нет: {ids}",
        "points": "Точки сдачи: {n}",
        "off": "    выкл: {items}",
        "routes": "Маршруты подписания:",
        "pairs": "пар: {n}",
        "skipped": "    не вошли: {items}",
        "may_add": "    можно добавить: {items}",
        "checks": "Проверки: {n} включены из {total}",
        "checks_none": "Проверки: не посчитаны (include: checks)",
        "branches": "Что если сменить вводную:",
        "branches_none": "Ветки: не посчитаны (include: branches)",
        "no_file_name": "имя задаёт шаблон",
        "example": "набор",
        "inputs_all": "Вводные: ",
        "inputs_given": "Вводные заданы: {given}; остальные по умолчанию",
        "inputs_default": "Вводные: все по умолчанию",
        "summary": "Сводка: ",
        "warnings": "Предупреждения ({n}):",
        "no_warnings": "Предупреждений нет.",
        "trace": "Трасса ({n} решений за показанными элементами):",
        "out_of_scope": "Не входит в результат: ",
        "step_without_person": "точка {point}: шаг {n} ждёт «{persona}», а человека нет",
        "language_fallback": "документ {doc}: нет редакции на язык проекта, берётся язык шаблона",
    },
    "en": {
        "documents": "Documents: {n} in the bundle of {total}",
        "meta": "Project fields: {n} visible of {total}",
        "meta_hidden": "  hidden: {ids}",
        "forms": "Forms: {n} apply of {total}",
        "form_fields": "{shown} fields visible, {required} required",
        "form_off": "does not apply",
        "participants": "Participants: {n}",
        "absent": "  absent: {ids}",
        "points": "Submission points: {n}",
        "off": "    off: {items}",
        "routes": "Signing routes:",
        "pairs": "pairs: {n}",
        "skipped": "    skipped: {items}",
        "may_add": "    may be added: {items}",
        "checks": "Checks: {n} enabled of {total}",
        "checks_none": "Checks: not calculated (include: checks)",
        "branches": "What if an input changes:",
        "branches_none": "Branches: not calculated (include: branches)",
        "no_file_name": "name set by the template",
        "example": "example",
        "inputs_all": "Inputs: ",
        "inputs_given": "Inputs set: {given}; the rest are defaults",
        "inputs_default": "Inputs: all defaults",
        "summary": "Summary: ",
        "warnings": "Warnings ({n}):",
        "no_warnings": "No warnings.",
        "trace": "Trace ({n} decisions behind the shown elements):",
        "out_of_scope": "Not covered: ",
        "step_without_person": "point {point}: step {n} waits for “{persona}” who is absent",
        "language_fallback": "document {doc}: no edition in the project language, the template language is used",
    },
}


def tr(lang: str, key: str, **kw: object) -> str:
    return _TEXT["en" if lang == "en" else "ru"][key].format(**kw)


@dataclass(frozen=True, slots=True)
class ViewOptions:
    sections: tuple[str, ...] = DEFAULT_SECTIONS
    detail: Detail = "compact"
    trace: bool = False
    lang: str = "ru"
    # Вводные, которые задал вызывающий (остальные взяты по умолчанию).
    requested: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class OutcomeView:
    text: str
    data: dict[str, Any]
    truncated: bool = False


def loc(value: object, lang: str) -> str:
    """Локализованная подпись `{ru, en}`: язык интерфейса, затем любой."""
    if isinstance(value, Mapping):
        picked = value.get(lang) or value.get("ru") or value.get("en") or next(iter(value.values()), "")
        return str(picked)
    return "" if value is None else str(value)


def dump(value: object) -> str:
    """Структурный ответ без отступов: токены дороже читаемости."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# ── условия и причины ────────────────────────────────────────────────────────


def _term(term: Mapping[str, Any]) -> str:
    op, subject, expected = term["op"], term["subject"], ", ".join(map(str, term.get("expected") or ()))
    match op:
        case "in":
            return f"{subject} in [{expected}]"
        case "equals":
            return f"{subject} = {expected}"
        case "contains_any":
            return f"{subject} contains any of [{expected}]"
        case "present":
            return f"{subject} is present"
        case "truthy":
            return f"{subject} is on"
    return f"{subject} {op} {expected}".strip()


def condition_of(entry: Mapping[str, Any]) -> str:
    """Условие решения: термы через `and` или `or`, фактические значения в скобках."""
    joiner = " or " if entry.get("join") == "any" else " and "
    cond = joiner.join(_term(t) for t in entry.get("terms") or ())
    actual = ", ".join(f"{k}={v}" for k, v in (entry.get("actual") or {}).items())
    return f"{cond} ({actual})" if actual else cond


def _reason(why: Sequence[str], trace: Mapping[str, Mapping[str, Any]]) -> str:
    """Почему элемента нет: первое невыполненное решение из его цепочки (дальше цепочка не идёт)."""
    for trace_id in why:
        entry = trace.get(trace_id)
        if entry is not None and entry.get("status") == "not_held":
            return f"{entry.get('kind')}: {condition_of(entry)}"
    return ""


def _tag(item: Mapping[str, Any], opts: ViewOptions) -> str:
    why = item.get("why") or ()
    return f" [{','.join(why)}]" if opts.trace and why else ""


def _without_why(value: Any) -> Any:
    """Структура без `why`: без трассы ссылки на решения ничего не говорят."""
    if isinstance(value, Mapping):
        return {k: _without_why(v) for k, v in value.items() if k != "why"}
    if isinstance(value, list):
        return [_without_why(v) for v in value]
    return value


def _why_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "why" and isinstance(item, list):
                found.update(str(x) for x in item)
            else:
                found |= _why_ids(item)
    elif isinstance(value, list):
        for item in value:
            found |= _why_ids(item)
    return found


# ── предупреждения ───────────────────────────────────────────────────────────


def warnings_of(body: Mapping[str, Any], lang: str) -> list[dict[str, str]]:
    """Что стоит знать автору шаблона. Поля `warnings` в схеме результата нет, предупреждения выводятся здесь."""
    found: list[dict[str, str]] = []
    present = {p["persona"] for p in body.get("participants") or () if p.get("present")}
    for point in body.get("points") or ():
        # Шаг ждёт человека, которого нет в комбинации (движок так считает, экран и линтер это показывают).
        for number, step in enumerate((point.get("route") or {}).get("steps") or (), start=1):
            found.extend(
                {
                    "code": "step_without_person",
                    "text": tr(lang, "step_without_person", point=point["id"], n=number, persona=person["persona"]),
                }
                for person in step
                if person["persona"] not in present
            )
    found.extend(
        {"code": "language_fallback", "text": tr(lang, "language_fallback", doc=doc["id"])}
        for doc in body.get("documents") or ()
        if doc.get("state") == "active" and doc.get("lang_state") == "fallback"
    )
    return found


# ── разделы: текст и структура ───────────────────────────────────────────────

Built = tuple[list[str], Any]
Builder = Callable[[Mapping[str, Any], ViewOptions, Mapping[str, Mapping[str, Any]]], Built]


def _files_of(doc: Mapping[str, Any], lang: str) -> str:
    names = []
    for inst in doc.get("instances") or ():
        name = inst.get("file_name") or f"({tr(lang, 'no_file_name')})"
        names.append(f"{inst['owner']}: {name}" if inst.get("owner") else name)
    return "; ".join(names)


def _chosen_variant(doc: Mapping[str, Any]) -> str | None:
    return next((v["id"] for v in doc.get("variants") or () if v.get("chosen")), None)


def _documents(body: Mapping[str, Any], opts: ViewOptions, trace: Mapping[str, Mapping[str, Any]]) -> Built:
    docs = body["documents"]
    active = [d for d in docs if d["state"] == "active"]
    lines = [tr(opts.lang, "documents", n=len(active), total=len(docs))]
    data: list[dict[str, Any]] = []
    for doc in docs:
        reason = "" if doc["state"] == "active" else _reason(doc.get("why") or (), trace)
        variant = _chosen_variant(doc)
        if doc["state"] == "active":
            extra = f" variant={variant}" if variant else ""
            if opts.detail == "full":
                extra += (
                    f" [{doc['scope']}, {doc.get('group') or '-'}, langs={','.join(doc['languages'])}, "
                    f"{doc['lang_state']}{', required' if doc['required'] else ''}, src={doc.get('source_file')}]"
                )
            lines.append(f"  + {doc['id']}: {_files_of(doc, opts.lang)}{extra}{_tag(doc, opts)}")
        else:
            lines.append(f"  - {doc['id']}: {doc['state']}{f' ({reason})' if reason else ''}{_tag(doc, opts)}")
        data.append(
            {
                "id": doc["id"],
                "state": doc["state"],
                "name": loc(doc["name"], opts.lang),
                "files": [{"owner": i.get("owner"), "file": i.get("file_name")} for i in doc["instances"]],
                **({"variant": variant} if variant else {}),
                **({"reason": reason} if reason else {}),
                **({"why": doc["why"]} if opts.trace and doc.get("why") else {}),
            }
        )
    return lines, data


def _meta(body: Mapping[str, Any], opts: ViewOptions, trace: Mapping[str, Mapping[str, Any]]) -> Built:
    fields = body["meta"]
    visible = [f for f in fields if f["visible"]]
    lines = [tr(opts.lang, "meta", n=len(visible), total=len(fields))]
    for f in visible:
        value = "-" if f.get("value") is None else f["value"]
        lines.append(f"  {f['id']} = {value} [{f['required_at']}]{_tag(f, opts)}")
    hidden = [f["id"] for f in fields if not f["visible"]]
    if hidden:
        lines.append(tr(opts.lang, "meta_hidden", ids=", ".join(hidden)))
    data = [
        {"id": f["id"], "visible": f["visible"], "required_at": f["required_at"], "value": f.get("value")}
        for f in fields
    ]
    return lines, data


def _forms(body: Mapping[str, Any], opts: ViewOptions, trace: Mapping[str, Mapping[str, Any]]) -> Built:
    forms = body["forms"]
    applied = [f for f in forms if f["applies"]]
    lines = [tr(opts.lang, "forms", n=len(applied), total=len(forms))]
    data: list[dict[str, Any]] = []
    for form in forms:
        shown = [f for f in form["fields"] if f["visible"]]
        required = [f for f in shown if f["required"]]
        if form["applies"]:
            counts = tr(opts.lang, "form_fields", shown=len(shown), required=len(required))
            lines.append(f"  {form['id']}: {counts}{_tag(form, opts)}")
            if opts.detail == "full":
                lines.extend(f"    {f['id']}{' *' if f['required'] else ''}" for f in shown)
        else:
            lines.append(f"  {form['id']}: {tr(opts.lang, 'form_off')}{_tag(form, opts)}")
        data.append(
            {
                "id": form["id"],
                "applies": form["applies"],
                "fields": [f["id"] for f in shown],
                "required": [f["id"] for f in required],
            }
        )
    return lines, data


def _participants(body: Mapping[str, Any], opts: ViewOptions, trace: Mapping[str, Mapping[str, Any]]) -> Built:
    people = body["participants"]
    present = [p for p in people if p["present"]]
    lines = [tr(opts.lang, "participants", n=len(present))]
    for p in present:
        role = f" ({p['role']})" if p["role"] != p["persona"] else ""
        org = f", {p['org']}" if p.get("org") else ""
        lines.append(f"  {p['persona']}{role}{org}{_tag(p, opts)}")
    absent = [p["persona"] for p in people if not p["present"]]
    if absent:
        lines.append(tr(opts.lang, "absent", ids=", ".join(absent)))
    data = [{"persona": p["persona"], "role": p["role"], "org": p.get("org"), "present": p["present"]} for p in people]
    return lines, data


def _points(body: Mapping[str, Any], opts: ViewOptions, trace: Mapping[str, Mapping[str, Any]]) -> Built:
    points = body["points"]
    lines = [tr(opts.lang, "points", n=len(points))]
    data: list[dict[str, Any]] = []
    for point in points:
        on = [i for i in point["items"] if i["active"]]
        # Пункт документа, которого в проекте нет (`absent`), показывает только подробный вид: он не про эту комбинацию.
        off = [i for i in point["items"] if not i["active"] and (opts.detail == "full" or i["off_reason"] != "absent")]
        names = [f"{i['doc_id']}({'+'.join(i['signatures'])})" if opts.detail == "full" else i["doc_id"] for i in on]
        title = loc(point["name"], opts.lang)
        lines.append(f"  {point['id']} ({title}): {', '.join(names) or '-'}{_tag(point, opts)}")
        if off:
            lines.append(tr(opts.lang, "off", items=", ".join(f"{i['doc_id']} ({i['off_reason']})" for i in off)))
        for extra in point["extra_items"]:
            state = "" if extra["active"] else f" ({extra['off_reason']})"
            lines.append(f"    + {extra['source']} -> {extra['output_name']}{state}")
        data.append(
            {
                "id": point["id"],
                "items": [i["doc_id"] for i in on],
                "off": [{"doc": i["doc_id"], "reason": i["off_reason"]} for i in off],
                "extra": [
                    {"source": e["source"], "output_name": e["output_name"], "active": e["active"]}
                    for e in point["extra_items"]
                ],
            }
        )
    return lines, data


def _when(when: Mapping[str, Any] | None) -> str:
    if not when:
        return ""
    role = when.get("role")
    return f" if {when['person']}" + (f"={role}" if role else " present")


def _route(body: Mapping[str, Any], opts: ViewOptions, trace: Mapping[str, Mapping[str, Any]]) -> Built:
    lines = [tr(opts.lang, "routes")]
    data: list[dict[str, Any]] = []
    for point in body["points"]:
        route = point["route"]
        steps = " -> ".join("[" + ", ".join(p["persona"] for p in step) + "]" for step in route["steps"]) or "-"
        lines.append(f"  {point['id']}: {steps}; {tr(opts.lang, 'pairs', n=len(route['pairs']))}{_tag(route, opts)}")
        by_doc: dict[str, list[str]] = {}
        for pair in route["pairs"]:
            mark = ("?" if pair["optional"] else "") + (_when(pair.get("when")) if opts.detail == "full" else "")
            by_doc.setdefault(pair["doc_id"], []).append(f"{pair['slot_id']}{mark}{_tag(pair, opts)}")
        lines.extend(f"    {doc}: {', '.join(slots)}" for doc, slots in by_doc.items())
        skipped = [f"{s['doc_id']}/{s['slot_id']}" for s in route["skipped"]]
        may_add = [f"{s['doc_id']}/{s['slot_id']}" for s in route["may_add"]]
        if skipped:
            lines.append(tr(opts.lang, "skipped", items=", ".join(skipped)))
        if may_add:
            lines.append(tr(opts.lang, "may_add", items=", ".join(may_add)))
        data.append(
            {
                "point": point["id"],
                "steps": [[p["persona"] for p in step] for step in route["steps"]],
                "pairs": [
                    {
                        "doc": p["doc_id"],
                        "slot": p["slot_id"],
                        "persona": p["persona"],
                        **({"optional": True} if p["optional"] else {}),
                        **({"when": p["when"]} if p.get("when") else {}),
                    }
                    for p in route["pairs"]
                ],
                "skipped": skipped,
                "may_add": may_add,
                "order": route["order_source"],
            }
        )
    return lines, data


def _checks(body: Mapping[str, Any], opts: ViewOptions, trace: Mapping[str, Mapping[str, Any]]) -> Built:
    rules = body.get("checks")
    if rules is None:
        return [tr(opts.lang, "checks_none")], None
    on = [r for r in rules if r["enabled"]]
    lines = [tr(opts.lang, "checks", n=len(on), total=len(rules))]
    if opts.detail == "full":
        lines.extend(f"  + {r['id']} ({r['severity']}, {r['engine']})" for r in on)
    lines.extend(f"  - {r['id']}: {r['off_reason']}" for r in rules if not r["enabled"])
    data = [
        {"id": r["id"], "enabled": r["enabled"], "off_reason": r["off_reason"], "severity": r["severity"]}
        for r in rules
    ]
    return lines, data


def _branches(body: Mapping[str, Any], opts: ViewOptions, trace: Mapping[str, Mapping[str, Any]]) -> Built:
    branches = body.get("branches")
    if branches is None:
        return [tr(opts.lang, "branches_none")], None
    lines = [tr(opts.lang, "branches")]
    data: list[dict[str, Any]] = []
    for branch in branches:
        alts = []
        for alt in branch["alternatives"]:
            delta = " ".join(f"{d['section']}+{d['added']}~{d['changed']}-{d['removed']}" for d in alt["delta"])
            alts.append(f"{alt['value']}: {delta or '='}")
        lines.append(f"  {branch['input']} = {branch['chosen']}; " + "; ".join(alts))
        data.append(
            {
                "input": branch["input"],
                "chosen": branch["chosen"],
                "alternatives": [
                    {
                        "value": a["value"],
                        "delta": {d["section"]: [d["added"], d["changed"], d["removed"]] for d in a["delta"]},
                    }
                    for a in branch["alternatives"]
                ],
            }
        )
    return lines, data


_BUILDERS: Final[dict[str, Builder]] = {
    "documents": _documents,
    "meta": _meta,
    "forms": _forms,
    "participants": _participants,
    "points": _points,
    "route": _route,
    "checks": _checks,
    "branches": _branches,
}


# ── трасса ───────────────────────────────────────────────────────────────────


def _trace_line(entry: Mapping[str, Any]) -> str:
    rule = entry["rule"]
    where = f"{rule['file']}#{rule['pointer']}" if rule["origin"] == "manifest" else f"builtin:{rule['builtin']}"
    subjects = [f"{s['section']}:{s['id']}" for s in entry["subjects"]]
    more = f" +{len(subjects) - _MAX_SUBJECTS}" if len(subjects) > _MAX_SUBJECTS else ""
    return (
        f"  {entry['id']} {entry['status']} {entry['effect']} {entry['kind']}: {condition_of(entry)} | {where}"
        f" | {', '.join(subjects[:_MAX_SUBJECTS])}{more}"
    )


# ── сборка вида ──────────────────────────────────────────────────────────────


def _summary(body: Mapping[str, Any]) -> dict[str, int]:
    return {s["section"]: s["count"] for s in body["digest"]["sections"] if s["section"] != "checks" or body["checks"]}


def section_of(body: Mapping[str, Any], name: str) -> Any:
    """Раздел как в ответе. `route` в ответе живёт внутри точек, поэтому собирается из них."""
    if name == "route":
        return [{"point": p["id"], **p["route"]} for p in body["points"]]
    if name == "points":
        return [{k: v for k, v in p.items() if k != "route"} for p in body["points"]]
    return body.get(name)


def _header(body: Mapping[str, Any], opts: ViewOptions, ref: str, summary: Mapping[str, int]) -> list[str]:
    lang = opts.lang
    revision = str(body["revision"])[:19]
    lines = [
        (
            f"{ref} [{body['state']}], {tr(lang, 'example')} {body['example']}, "
            f"fingerprint {body['fingerprint']}, revision {revision}"
        )
    ]
    given = ", ".join(f"{k}={v}" for k, v in (opts.requested or {}).items())
    if opts.detail == "full":
        lines.append(tr(lang, "inputs_all") + ", ".join(f"{k}={v}" for k, v in body["inputs"].items()))
    else:
        lines.append(tr(lang, "inputs_given", given=given) if given else tr(lang, "inputs_default"))
    lines.append(tr(lang, "summary") + ", ".join(f"{k} {v}" for k, v in summary.items()))
    return lines


def build_view(body: Mapping[str, Any], opts: ViewOptions) -> OutcomeView:
    """Текст и структура результата: сводка, выбранные разделы, предупреждения, трасса по запросу."""
    lang = opts.lang
    trace = {entry["id"]: entry for entry in body["trace"]}
    summary = _summary(body)
    warnings = warnings_of(body, lang)
    ref = f"{body['pack']}/{body['template']}/{body['version']}"
    lines = _header(body, opts, ref, summary)

    sections: dict[str, Any] = {}
    shown: dict[str, Any] = {}
    for name in SECTIONS:
        if name not in opts.sections:
            continue
        section_lines, compact = _BUILDERS[name](body, opts, trace)
        lines.extend(section_lines)
        raw = section_of(body, name)
        shown[name] = raw
        if opts.detail == "full":
            sections[name] = raw if opts.trace else _without_why(raw)
        else:
            sections[name] = compact

    if warnings:
        lines.append(tr(lang, "warnings", n=len(warnings)))
        lines.extend(f"  ! {w['text']}" for w in warnings)
    else:
        lines.append(tr(lang, "no_warnings"))

    data: dict[str, Any] = {
        "version": ref,
        "state": body["state"],
        "example": body["example"],
        "revision": body["revision"],
        "fingerprint": body["fingerprint"],
        "inputs": body["inputs"],
        "summary": summary,
        "warnings": warnings,
        "sections": sections,
    }
    truncated = False
    if opts.trace:
        wanted = _why_ids(shown)
        entries = [e for e in body["trace"] if e["id"] in wanted]
        truncated = len(entries) > MAX_TRACE
        entries = entries[:MAX_TRACE]
        lines.append(tr(lang, "trace", n=len(entries)))
        lines.extend(_trace_line(e) for e in entries)
        data["trace"] = entries
    if opts.detail == "full":
        data["out_of_scope"] = body["out_of_scope"]
        lines.append(tr(lang, "out_of_scope") + ", ".join(body["out_of_scope"]))
    return OutcomeView("\n".join(lines), data, truncated)


def split_sections(raw: Iterable[str]) -> tuple[str, ...]:
    """Имена разделов из аргумента: порядок результата, повторы убраны."""
    wanted = set(raw)
    return tuple(s for s in SECTIONS if s in wanted)
