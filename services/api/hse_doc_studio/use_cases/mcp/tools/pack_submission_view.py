"""Текстовый вид `pack_submission`: профили сдачи как их записал автор пака и «Маршрут в этой комбинации».

Записанное (`submission_lines`): порядок версии, у каждой точки пункты с подписями, порядок маршрута точки по шагам
и слоты сверх точки с условием `when` и отметкой «необязательна». Посчитанное на комбинации (`routes_lines`,
`routes: true`): шаги людьми из набора данных, подписи по документам с тем, кто подписывает, откуда подпись, условием
и необязательностью, слоты, которые условие не пропустило, и пункты, которые в комбинации не сдаются. Чистые функции
над моделями `core/pack_studio/submission.py`, структурный ответ (`format: json`) от них не зависит.
"""

from __future__ import annotations

from collections.abc import Sequence

from hse_doc_studio.core.pack_studio.submission import (
    Indexed,
    ItemEntry,
    PairSource,
    ProfileRoute,
    ProfileView,
    RoutePair,
    RoutePerson,
    SlotEntry,
    SubmissionRoutes,
    VersionSubmission,
    WhenCondition,
)
from hse_doc_studio.use_cases.mcp.tools.pack_outcome_view import loc

_ORDER_SOURCES = {
    "profile": "порядок точки (signing_route)",
    "version": "порядок версии (signatures.route)",
    "builtin": "встроенный порядок",
}


def steps_text(steps: Sequence[Sequence[str]]) -> str:
    """Шаги по порядку: «1. author; 2. supervisor, co_supervisor» (в одном шаге подписывают параллельно)."""
    return "; ".join(f"{number}. {', '.join(step)}" for number, step in enumerate(steps, start=1)) or "-"


def when_text(when: WhenCondition | None) -> str:
    """Условие слота: «если co_supervisor=company» (роль персоны) или «если есть co_supervisor» (персона задана)."""
    if when is None:
        return ""
    return f"если {when.person}={when.role}" if when.role else f"если есть {when.person}"


def _notes(*notes: str) -> str:
    kept = [note for note in notes if note]
    return f" ({', '.join(kept)})" if kept else ""


def _item(item: Indexed[ItemEntry]) -> str:
    entry = item.entry
    if entry is None:
        return f"[{item.index}] не читается: {item.error}"
    notes = _notes(
        "не сдаётся при NDA" if entry.skip_if_nda else "",
        f"только {', '.join(entry.supported_kinds)}" if entry.supported_kinds else "",
    )
    signatures = f": {', '.join(entry.signatures)}" if entry.signatures else ": без подписей"
    return f"{entry.doc_id}{signatures}{notes}"


def _slot(slot: Indexed[SlotEntry]) -> str:
    entry = slot.entry
    if entry is None:
        return f"[{slot.index}] не читается: {slot.error}"
    return f"{entry.doc_id}/{entry.slot_id}{_notes(when_text(entry.when), 'необязательна' if entry.optional else '')}"


def _profile(profile: ProfileView, lang: str) -> list[str]:
    name = loc(profile.name, lang) if profile.name else ""
    lines = [f"  профиль {profile.index}: {profile.id or '?'}" + (f" «{name}»" if name else "")]
    if profile.error:
        lines.append(f"    не читается: {profile.error}")
    lines += [f"    пункт {_item(item)}" for item in profile.items]
    if profile.extra_items:
        lines.append(f"    файлов сверх документов: {len(profile.extra_items)}")
    if profile.signing_route is None:
        lines.append("    порядок точки не задан: действует порядок версии")
    else:
        lines.append(f"    порядок точки (signing_route): {steps_text(profile.signing_route)}")
    if profile.signing_slots:
        lines.append("    слоты сверх точки (signing_slots):")
        lines += [f"      {_slot(slot)}" for slot in profile.signing_slots]
    return lines


def submission_lines(sub: VersionSubmission, lang: str) -> list[str]:
    """Записанные маршруты: порядок версии и точки по порядку манифеста."""
    if sub.route is None:
        lines = [f"Порядок версии не задан, встроенный: {steps_text(sub.builtin_route)}"]
    else:
        lines = [f"Порядок версии (signatures.route): {steps_text(sub.route)}"]
    for profile in sub.profiles:
        lines += _profile(profile, lang)
    return lines


def _person(person: RoutePerson) -> str:
    role = "" if person.role == person.persona else f" ({person.role})"
    return f"{person.persona}{role}" + (f" {person.name}" if person.name else "")


def _pair(pair: RoutePair) -> str:
    who = "" if pair.persona == pair.slot_id else f" [{pair.persona}]"
    notes = _notes(
        "сверх точки" if pair.source is PairSource.preset else "",
        when_text(pair.when),
        "необязательна" if pair.optional else "",
    )
    return f"{pair.slot_id}{who}{notes}"


def _route(route: ProfileRoute) -> list[str]:
    source = _ORDER_SOURCES.get(route.order_source, route.order_source)
    lines = [f"  {route.id}: {source}" + ("" if route.preset else "; пресета шаблона нет")]
    if not route.steps:
        lines.append("    подписи точке не нужны")
    lines += [
        f"    шаг {number}: {'; '.join(_person(person) for person in step)}"
        for number, step in enumerate(route.steps, start=1)
    ]
    by_doc: dict[str, list[str]] = {}
    for pair in route.pairs:
        by_doc.setdefault(pair.doc_id, []).append(_pair(pair))
    lines += [f"    подписи {doc}: {', '.join(slots)}" for doc, slots in by_doc.items()]
    if route.skipped:
        skipped = ", ".join(f"{s.doc_id}/{s.slot_id}{_notes(when_text(s.when))}" for s in route.skipped)
        lines.append(f"    условие не пропустило: {skipped}")
    if route.may_add:
        lines.append(f"    автор проекта может добавить: {', '.join(f'{doc}/{slot}' for doc, slot in route.may_add)}")
    if route.items_off:
        lines.append(f"    не сдаются в этой комбинации: {', '.join(route.items_off)}")
    return lines


def routes_lines(routes: SubmissionRoutes) -> list[str]:
    """«Маршрут в этой комбинации» каждой точки: шаги людьми и подписи с тем, кто их ставит."""
    combo = ", ".join(f"{key}={value}" for key, value in routes.combination.items())
    lines = [f"Маршруты в комбинации (набор {routes.example}; {combo}): профилей {len(routes.profiles)}"]
    for route in routes.profiles:
        lines += _route(route)
    return lines
