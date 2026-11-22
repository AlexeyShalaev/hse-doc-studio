"""Слова интерфейса Студии шаблонов для ответов MCP (pack-studio-mcp.md, P3 и P4).

Находки линтера результата и главная кнопка «Изменений» называются так же, как их показывает интерфейс
(`features/pack-space/plain/findings.ts`, `changes/` и `next-step/`): заголовок и «Как исправить» по коду правила,
названия документов, подписей и точек сдачи из пака. Тексты лежат в `pack_plain_texts.json` (ru, en), тест сверяет
их со строками интерфейса (`packSpace/plain.json`, `check.json`, `changes.json`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Final

from hse_doc_studio.core.i18n import current_interface_language

_TEXTS: Final = Path(__file__).with_name("pack_plain_texts.json")

LINT_RULES: Final = frozenset(
    {
        "slot-never-routed",
        "route-step-without-person",
        "route-gap",
        "visible-if-unknown-field",
        "visible-if-value-not-in-options",
        "required-hidden",
        "field-never-visible",
        "variant-lang-outside-langs",
        "skip-if-nda-without-nda",
        "when-unknown-person",
        "when-never-held",
        "when-always-held",
        "slot-when-overlap",
        "document-never-active",
        "item-never-active",
        "point-empty",
        "translation-missing",
        "builtin-gate-mismatch",
        "dimension-no-effect",
        "jinja-fail-open",
        "jinja-unknown-meta-key",
        "atlas-skipped",
    }
)

_PLACEHOLDER: Final = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_QUOTED: Final = re.compile(r"«([^»]*)»")
_SHARE: Final = re.compile(r"в\s+(\d+)\s+из\s+(\d+)")
_AUTHOR_N: Final = re.compile(r"^author(\d+)$")


@cache
def _all_texts() -> dict[str, Any]:
    return dict(json.loads(_TEXTS.read_text(encoding="utf-8")))


def texts(lang: str | None = None) -> Mapping[str, Any]:
    """Тексты языка интерфейса (`ru` или `en`)."""
    return _all_texts()[lang or current_interface_language().value]


def lookup(key: str, lang: str | None = None) -> str | None:
    node: Any = texts(lang)
    for part in key.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def fill(template: str, params: Mapping[str, object]) -> str:
    """Подстановка `{{name}}` как у i18next; неизвестное имя остаётся пустым."""
    return _PLACEHOLDER.sub(lambda m: str(params.get(m.group(1), "")), template)


def say(key: str, params: Mapping[str, object] | None = None, lang: str | None = None) -> str:
    template = lookup(key, lang)
    return fill(template, params or {}) if template is not None else key


def _pick(localized: Mapping[str, str] | None, lang: str) -> str | None:
    if not localized:
        return None
    return localized.get(lang) or localized.get("ru") or next(iter(localized.values()), None)


@dataclass(frozen=True)
class Naming:
    """Названия для людей (как `makeNaming` интерфейса): чего нет в паке, получает нейтральное слово."""

    lang: str
    documents: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    slots: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    points: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    inputs: Mapping[str, str] = field(default_factory=dict)

    def _fallback(self, kind: str) -> str:
        return say(f"plain.fallback.{kind}", lang=self.lang)

    def role(self, ident: str) -> str:
        n = _AUTHOR_N.match(ident)
        if n:
            return say("plain.role.authorN", {"n": n.group(1)}, self.lang)
        label = _pick(self.slots.get(ident), self.lang)
        if label:
            return label
        return lookup(f"plain.role.{ident}", self.lang) or self._fallback("role")

    def slot(self, ident: str) -> str:
        label = _pick(self.slots.get(ident), self.lang)
        if label:
            return label
        if _AUTHOR_N.match(ident) or lookup(f"plain.role.{ident}", self.lang) is not None:
            return self.role(ident)
        return self._fallback("slot")

    def document(self, ident: str) -> str:
        return _pick(self.documents.get(ident), self.lang) or self._fallback("document")

    def point(self, ident: str) -> str:
        return _pick(self.points.get(ident), self.lang) or self._fallback("point")

    def input(self, ident: str) -> str:
        """Подпись условия: из пака, словарь стандартных условий, иначе сам id (как `useSituationLabels`)."""
        return self.inputs.get(ident) or lookup(f"situation.std.{ident}", self.lang) or ident

    def value(self, ident: str, value: str) -> str:
        if value in {"yes", "no"} and not lookup(f"situation.values.{ident}.{value}", self.lang):
            return lookup(f"situation.{value}", self.lang) or value
        return lookup(f"situation.values.{ident}.{value}", self.lang) or value

    def language(self, code: str) -> str:
        return lookup(f"plain.lang.{code}", self.lang) or code.upper()


def naming_of(version: Any, inputs: Sequence[Mapping[str, Any]] = (), lang: str | None = None) -> Naming:
    """Названия из модели версии (`TemplateVersion`: документы, слоты, точки сдачи) и вводных результата."""
    labels: dict[str, str] = {}
    code = lang or current_interface_language().value
    for item in inputs:
        label = item.get("label")
        text = _pick(label, code) if isinstance(label, Mapping) else label if isinstance(label, str) else None
        if text:
            labels[str(item.get("id"))] = text
    return Naming(
        lang=code,
        documents={d.id: dict(d.name) for d in version.documents},
        slots={s.id: dict(s.label) for s in version.signatures_config.slots},
        points={p.id: dict(p.name) for p in version.pack_submission.profiles},
        inputs=labels,
    )


def _list_after(text: str, pattern: str) -> list[str]:
    match = re.search(pattern, text)
    raw = match.group(1) if match else ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def _file_document(file: str | None) -> str | None:
    match = re.match(r"^files/([^/!]+)/", file or "")
    return match.group(1) if match else None


def _ends(finding: Mapping[str, Any], tail: str) -> bool:
    return str(finding.get("pointer") or "").endswith(tail)


def _parts(finding: Mapping[str, Any], naming: Naming) -> tuple[str, dict[str, str], bool]:  # noqa: C901, PLR0911, PLR0912 — таблица правил интерфейса
    """Вариант текста и подстановки (повтор `partsOf` из `plain/findings.ts`)."""
    rule = str(finding.get("rule_id"))
    message = str(finding.get("message") or "")
    quoted = _QUOTED.findall(message)

    def at(index: int) -> str:
        return quoted[index] if index < len(quoted) else ""

    elements = finding.get("elements") or []
    first = elements[0] if elements and isinstance(elements[0], Mapping) else {}
    if rule == "slot-never-routed":
        return rule, {"signature": naming.slot(at(0))}, False
    if rule == "route-step-without-person":
        people = ", ".join(naming.role(i) for i in _list_after(message, r"нет в проекте:\s*(.+?)\s*\(в \d+"))
        return (
            rule,
            {"point": naming.point(at(0)), "people": people or say("plain.fallback.role", lang=naming.lang)},
            True,
        )
    if rule == "route-gap":
        return rule, {"point": naming.point(at(0))}, True
    if rule == "required-hidden":
        section = first.get("section")
        return f"{rule}.{'form' if section == 'forms' else 'meta' if section == 'meta' else 'other'}", {}, False
    if rule == "variant-lang-outside-langs":
        langs = ", ".join(naming.language(c) for c in _list_after(message, r"называет\s+(.+?),\s+а\s"))
        return (
            f"{rule}.{'langs' if langs else 'plain'}",
            {"document": naming.document(str(first.get("id") or "")), "langs": langs},
            False,
        )
    if rule == "skip-if-nda-without-nda":
        return rule, {"document": naming.document(at(0)), "point": naming.point(at(1))}, False
    if rule == "when-unknown-person":
        kind = "slot" if _ends(finding, "/slot_id") else "document" if _ends(finding, "/doc_id") else "person"
        return f"{rule}.{kind}", {}, False
    if rule in {"when-never-held", "when-always-held"}:
        return (
            rule,
            {"signature": naming.slot(at(0)), "document": naming.document(at(1)), "point": naming.point(at(2))},
            False,
        )
    if rule == "slot-when-overlap":
        return (
            rule,
            {"point": naming.point(at(0)), "signature": naming.slot(at(1)), "document": naming.document(at(2))},
            False,
        )
    if rule == "document-never-active":
        return rule, {"document": naming.document(at(0))}, False
    if rule == "item-never-active":
        return rule, {"document": naming.document(at(0)), "point": naming.point(at(1))}, False
    if rule == "point-empty":
        n = re.search(r"в\s+(\d+)\s+комбинациях", message)
        total = re.search(r"из\s+(\d+)\s+строк", message)
        everywhere = "во всех комбинациях" in message or not n or not total
        return (
            f"{rule}.{'all' if everywhere else 'some'}",
            {"point": naming.point(at(0)), "n": n.group(1) if n else "", "total": total.group(1) if total else ""},
            False,
        )
    if rule == "translation-missing":
        langs = ", ".join(
            naming.language(c) for c in _list_after(message, r"нет перевода .+? на\s+([a-z, ]+?)\s*\(языки")
        )
        kind = "hint" if _ends(finding, "/help") else "name"
        return f"{rule}.{kind}", {"langs": langs or say("plain.fallback.lang", lang=naming.lang)}, False
    if rule == "builtin-gate-mismatch":
        if _ends(finding, "/options"):
            variant = "manualsOptions"
        elif message.startswith("Документ «nda»"):
            variant = "ndaDocument"
        elif message.startswith("Поле проекта nda"):
            variant = "ndaField"
        else:
            variant = "manualsField"
        return f"{rule}.{variant}", {}, False
    if rule == "dimension-no-effect":
        return rule, {"condition": naming.input(at(0))}, False
    if rule in {"jinja-fail-open", "jinja-unknown-meta-key"}:
        doc = _file_document(finding.get("file"))
        name = naming.document(doc) if doc else say("plain.fallback.document", lang=naming.lang)
        return rule, {"document": name}, False
    if rule == "atlas-skipped":
        rows = re.search(r"\((\d+)\s+строк", message)
        limit = re.search(r"предела\s+(\d+)", message)
        return (
            f"{rule}.{'numbers' if rows and limit else 'plain'}",
            {"rows": rows.group(1) if rows else "", "limit": limit.group(1) if limit else ""},
            False,
        )
    return rule, {}, False


def plain_finding(finding: Mapping[str, Any], naming: Naming) -> dict[str, Any]:
    """Заголовок, «Как исправить» и дополнение находки словами интерфейса (`plainFinding`)."""
    lang = naming.lang
    rule = str(finding.get("rule_id"))
    if rule not in LINT_RULES:
        return {
            "title": str(finding.get("message") or ""),
            "how": str(finding.get("hint") or say("plain.finding.unknown.how", lang=lang)),
            "extra": None,
            "known": False,
        }
    key, params, share = _parts(finding, naming)
    counts = _SHARE.search(str(finding.get("message") or ""))
    extra = (
        say("plain.finding.share", {"n": counts.group(1), "total": counts.group(2)}, lang) if share and counts else None
    )
    return {
        "title": say(f"plain.finding.{key}.title", params, lang),
        "how": say(f"plain.finding.{key}.how", params, lang),
        "extra": extra,
        "known": True,
    }


def percent(value: float, lang: str) -> str:
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if lang == "ru" else text


def lint_plain_text(  # noqa: C901 — сводка, находки и покрытие, как вкладка
    body: Mapping[str, Any], naming: Naming, severity_order: Sequence[str], severity: str, limit: int
) -> tuple[str, bool]:
    """Текст вкладки «Проверка, Замечания»: сводка, находки словами интерфейса и покрытие готовыми случаями."""
    lang = naming.lang
    order = {name: index for index, name in enumerate(severity_order)}
    shown = [f for f in body["findings"] if order.get(f["severity"], 99) <= order.get(severity, 1)]
    lines = [say("issues.summary", {"errors": body["errors"], "warnings": body["warnings"]}, lang)]
    if body.get("infos"):
        lines.append(say("issues.infos", {"count": body["infos"]}, lang))
    if body.get("atlas_skipped"):
        lines.append(f"{say('issues.skippedTitle', lang=lang)}. {say('issues.skippedLead', lang=lang)}")
    if body.get("jinja") == "unavailable":
        lines.append(say("issues.textsUnavailable", lang=lang))
    for item in shown[:limit]:
        plain = plain_finding(item, naming)
        level = say(f"issues.severity.{item['severity']}", lang=lang)
        lines.append(f"- {level}: {plain['title']}")
        if plain["extra"]:
            lines.append(f"  {plain['extra']}")
        lines.append(f"  {say('issues.hint', lang=lang)} {plain['how']}")
        where = item.get("file") or ""
        if item.get("line"):
            where += f":{item['line']}"
        if item.get("pointer"):
            where += f" {item['pointer']}"
        lines.append(f"  [{item['rule_id']}{' ' + where if where else ''}]")
    if not shown:
        lines.append(say("issues.emptyTitle", lang=lang))
    cover = body.get("coverage") or {}
    if cover:
        lines.append(
            say("issues.coverage.percentLabel", {"percent": percent(float(cover.get("percent") or 0), lang)}, lang)
        )
        if cover.get("approximate"):
            lines.append(say("issues.coverage.approximate", lang=lang))
        lines.append(
            "; ".join(
                (
                    say("issues.coverage.full", {"count": cover.get("rules_covered", 0)}, lang),
                    say("issues.coverage.half", {"count": cover.get("rules_half", 0)}, lang),
                    say("issues.coverage.none", {"count": cover.get("rules_uncovered", 0)}, lang),
                )
            )
        )
        lines.append(say("issues.coverage.cases", {"count": cover.get("scenarios", 0)}, lang))
        rows = cover.get("uncovered_rows") or []
        if rows:
            lines.append(say("issues.coverage.rowsLabel", lang=lang) + ":")
            for row in rows[:8]:
                situation = "; ".join(f"{naming.input(k)}: {naming.value(k, str(v))}" for k, v in row["inputs"].items())
                lines.append(f"  {situation}. {say('issues.coverage.gain', {'count': row['gain']}, lang)}")
    return "\n".join(lines), len(shown) > limit


def next_step_label(kind: str, params: Mapping[str, object], lang: str | None = None) -> str:
    """Подпись главной кнопки (`changes.next.*`); у открытого запроса с известными проверками своя строка."""
    if kind == "request":
        checks = str(params.get("checks") or "unknown")
        key = "next.requestOpen" if checks == "unknown" else f"next.request.{checks}"
        return say(key, params, lang)
    return say(f"next.{kind}", params, lang)


def next_step_hint(kind: str, lang: str | None = None) -> str | None:
    return lookup(f"next.hint.{kind}", lang)
