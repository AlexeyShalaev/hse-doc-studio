"""Разделы результата «точки сдачи» и «маршрут»: пункты с причиной выключения, файлы сверх документов, шаги и пары.

Пункты считает общий предикат `item_off_reason` (его же зовут пакет сдачи и план подписей). Маршрут приходит готовым
от движка (`profile_route`: точка, пресет, порядок по умолчанию), здесь он переводится в модель результата, а условия
`when` слотов сверх точки записываются в трассу вызовом того же `condition_met`, что решает движок.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from hse_doc_studio.core.pack_studio.outcome.facts import Facts, yes_no
from hse_doc_studio.core.pack_studio.outcome.model import (
    DocSlot,
    DocumentOutcome,
    ElementRef,
    PointExtra,
    PointItem,
    PointOutcome,
    RouteOutcome,
    RoutePair,
    RoutePerson,
    SkippedPair,
    Term,
    When,
)
from hse_doc_studio.core.pack_studio.outcome.predicates import item_off_reason, kind_allowed, kinds_restrict
from hse_doc_studio.core.pack_studio.outcome.trace import Tracer, builtin_rule, manifest_rule, why
from hse_doc_studio.core.signing_route.preset import condition_met

if TYPE_CHECKING:
    from hse_doc_studio.core.catalog import SigningSlotPreset, SubmissionProfile, TemplateVersion
    from hse_doc_studio.core.entities import Project
    from hse_doc_studio.core.pack_studio.submission import ProfileRoute
    from hse_doc_studio.core.pack_studio.submission import RoutePair as EnginePair
    from hse_doc_studio.core.pack_studio.submission import SkippedPair as EngineSkipped

VERSION_MANIFEST = "version.yaml"


def pair_id(point_id: str, doc_id: str, slot_id: str, persona: str) -> str:
    """Id пары маршрута: `<точка>/<документ>/<слот>`; у персоны не по слоту (автор команды) в конце персона."""
    base = f"{point_id}/{doc_id}/{slot_id}"
    return base if persona == slot_id else f"{base}/{persona}"


def step_id(point_id: str, number: int) -> str:
    """Id шага маршрута: `<точка>/step/<номер с 1>`."""
    return f"{point_id}/step/{number}"


def _doc_reasons(doc: DocumentOutcome | None, tracer: Tracer) -> tuple[str, ...]:
    """Решения документа, по которым пункта нет: его цепочка до первого невыполненного условия включительно."""
    if doc is None or doc.state == "active":
        return ()
    chain: list[str] = []
    for decision_id in doc.why:
        chain.append(decision_id)
        if tracer.status_of(decision_id) == "not_held":
            break
    return tuple(chain)


def _items(  # noqa: PLR0913 — профиль, факты, документы и трасса
    index: int,
    profile: SubmissionProfile,
    facts: Facts,
    documents: Mapping[str, DocumentOutcome],
    tracer: Tracer,
) -> tuple[PointItem, ...]:
    items: list[PointItem] = []
    for item_index, item in enumerate(profile.items):
        element = [ElementRef("points", f"{profile.id}/{item.doc_id}")]
        base = f"/pack_submission/profiles/{index}/items/{item_index}"
        ids: list[str] = []
        if kinds_restrict(item.supported_kinds):
            ids.append(
                tracer.decide(
                    rule=manifest_rule(VERSION_MANIFEST, f"{base}/supported_kinds"),
                    kind="item_kinds",
                    effect="gate",
                    terms=[Term("in", "kind", tuple(item.supported_kinds))],
                    actual={"kind": facts.kind},
                    status="held" if kind_allowed(item.supported_kinds, facts.kind) else "not_held",
                    subjects=element,
                )
            )
        if item.skip_if_nda:
            ids.append(
                tracer.decide(
                    rule=manifest_rule(VERSION_MANIFEST, f"{base}/skip_if_nda"),
                    kind="skip_if_nda",
                    effect="exclude",
                    terms=[Term("truthy", facts.nda_subject)],
                    actual={facts.nda_subject: yes_no(facts.nda)},
                    status="held" if facts.nda else "not_held",
                    subjects=element,
                )
            )
        doc = documents.get(item.doc_id)
        reason = item_off_reason(
            skip_if_nda=item.skip_if_nda,
            item_kinds=item.supported_kinds,
            kind=facts.kind,
            nda=facts.nda,
            doc_state=doc.state if doc is not None else "absent",
        )
        if reason in ("absent", "inactive"):
            ids.extend(_doc_reasons(doc, tracer))
        items.append(
            PointItem(
                doc_id=item.doc_id,
                active=reason is None,
                off_reason=reason,  # type: ignore[arg-type]
                signatures=tuple(item.signatures),
                why=why(*ids),
            )
        )
    return tuple(items)


def _extras(index: int, profile: SubmissionProfile, facts: Facts, tracer: Tracer) -> tuple[PointExtra, ...]:
    extras: list[PointExtra] = []
    for extra_index, extra in enumerate(profile.extra_items):
        allowed = kind_allowed(extra.supported_kinds, facts.kind)
        reasons: tuple[str, ...] = ()
        if kinds_restrict(extra.supported_kinds):
            reasons = why(
                tracer.decide(
                    rule=manifest_rule(
                        VERSION_MANIFEST, f"/pack_submission/profiles/{index}/extra_items/{extra_index}/supported_kinds"
                    ),
                    kind="extra_kinds",
                    effect="gate",
                    terms=[Term("in", "kind", tuple(extra.supported_kinds))],
                    actual={"kind": facts.kind},
                    status="held" if allowed else "not_held",
                    subjects=[ElementRef("points", f"{profile.id}/{extra.source}")],
                )
            )
        extras.append(
            PointExtra(
                source=extra.source,
                output_name=extra.output_name,
                format=extra.format,
                active=allowed,
                off_reason=None if allowed else "kind",
                why=reasons,
            )
        )
    return tuple(extras)


def _slot_entry(
    profile: SubmissionProfile, doc_id: str, slot_id: str, *, with_when: bool
) -> tuple[int, SigningSlotPreset] | None:
    """Запись `signing_slots` профиля для пары; `with_when`: ищем запись с условием (она объясняет слот сверх точки)."""
    return next(
        (
            (k, entry)
            for k, entry in enumerate(profile.signing_slots)
            if entry.doc_id == doc_id and entry.slot_id == slot_id and (entry.when is not None or not with_when)
        ),
        None,
    )


def _when_decision(  # noqa: PLR0913 — пара, запись пресета и факты
    index: int,
    k: int,
    entry: SigningSlotPreset,
    project: Project,
    facts: Facts,
    tracer: Tracer,
    element: ElementRef,
) -> str:
    condition = entry.when
    assert condition is not None  # noqa: S101 — вызывается только для записи с условием
    person = condition.person
    terms = [Term("present", person)]
    actual = {person: yes_no(facts.has_person(person))}
    if condition.role is not None:
        terms.append(Term("equals", f"{person}.role", (condition.role.value,)))
        actual[f"{person}.role"] = facts.person_role(person) or ""
    return tracer.decide(
        rule=manifest_rule(VERSION_MANIFEST, f"/pack_submission/profiles/{index}/signing_slots/{k}/when"),
        kind="slot_when",
        effect="add",
        terms=terms,
        actual=actual,
        status="held" if condition_met(condition, project) else "not_held",
        subjects=[element],
    )


def _order_decision(index: int, profile: SubmissionProfile, route: ProfileRoute, tracer: Tracer) -> str:
    """Откуда порядок маршрута: `signing_route` точки, `signatures.route` версии или встроенный порядок."""
    if route.order_source == "profile":
        rule = manifest_rule(VERSION_MANIFEST, f"/pack_submission/profiles/{index}/signing_route")
    elif route.order_source == "version":
        rule = manifest_rule(VERSION_MANIFEST, "/signatures/route")
    else:
        rule = builtin_rule("builtin_route")
    return tracer.decide(
        rule=rule,
        kind="route_order",
        effect="order",
        terms=[],
        actual={},
        status="held",
        subjects=[ElementRef("route", profile.id)],
    )


def _pair(  # noqa: PLR0913 — профиль, пара движка, проект, факты и трасса
    index: int, profile: SubmissionProfile, pair: EnginePair, project: Project, facts: Facts, tracer: Tracer
) -> RoutePair:
    element = ElementRef("route", pair_id(profile.id, pair.doc_id, pair.slot_id, pair.persona))
    ids: list[str] = []
    entry = _slot_entry(profile, pair.doc_id, pair.slot_id, with_when=pair.source.value == "preset")
    if entry is not None:
        k, preset = entry
        if preset.when is not None and pair.source.value == "preset":
            ids.append(_when_decision(index, k, preset, project, facts, tracer, element))
        if pair.optional and preset.optional:
            ids.append(
                tracer.decide(
                    rule=manifest_rule(
                        VERSION_MANIFEST, f"/pack_submission/profiles/{index}/signing_slots/{k}/optional"
                    ),
                    kind="slot_optional",
                    effect="require",
                    terms=[],
                    actual={},
                    status="held",
                    subjects=[element],
                )
            )
    return RoutePair(
        doc_id=pair.doc_id,
        slot_id=pair.slot_id,
        persona=pair.persona,
        source=pair.source.value,
        optional=pair.optional,
        when=When(pair.when.person, pair.when.role) if pair.when is not None else None,
        why=why(*ids),
    )


def _skipped(  # noqa: PLR0913 — профиль, пропущенная пара движка, проект, факты и трасса
    index: int, profile: SubmissionProfile, item: EngineSkipped, project: Project, facts: Facts, tracer: Tracer
) -> SkippedPair:
    element = ElementRef("route", f"{profile.id}/{item.doc_id}/{item.slot_id}")
    found = _slot_entry(profile, item.doc_id, item.slot_id, with_when=True)
    reasons = why(_when_decision(index, found[0], found[1], project, facts, tracer, element)) if found else ()
    return SkippedPair(
        doc_id=item.doc_id,
        slot_id=item.slot_id,
        when=When(item.when.person, item.when.role) if item.when is not None else None,
        why=reasons,
    )


def _route(  # noqa: PLR0913 — профиль, маршрут движка, проект, факты и трасса
    index: int,
    profile: SubmissionProfile,
    route: ProfileRoute,
    project: Project,
    facts: Facts,
    tracer: Tracer,
) -> RouteOutcome:
    order = _order_decision(index, profile, route, tracer)
    return RouteOutcome(
        steps=tuple(tuple(RoutePerson(p.persona, p.role, p.name) for p in step) for step in route.steps),  # type: ignore[arg-type]
        pairs=tuple(_pair(index, profile, pair, project, facts, tracer) for pair in route.pairs),
        skipped=tuple(_skipped(index, profile, item, project, facts, tracer) for item in route.skipped),
        may_add=tuple(DocSlot(doc_id, slot_id) for doc_id, slot_id in route.may_add),
        order_source=route.order_source,  # type: ignore[arg-type]
        preset=route.preset,
        why=why(order),
    )


def evaluate_points(  # noqa: PLR0913 — версия, проект, факты, документы, маршруты и трасса
    version: TemplateVersion,
    project: Project,
    facts: Facts,
    documents: tuple[DocumentOutcome, ...],
    routes: Mapping[str, ProfileRoute],
    tracer: Tracer,
) -> tuple[PointOutcome, ...]:
    by_id = {doc.id: doc for doc in documents}
    points: list[PointOutcome] = []
    profiles = version.pack_submission.profiles if version.pack_submission is not None else ()
    for index, profile in enumerate(profiles):
        route = routes[profile.id]
        items = _items(index, profile, facts, by_id, tracer)
        extras = _extras(index, profile, facts, tracer)
        points.append(
            PointOutcome(
                id=profile.id,
                index=index,
                name=dict(profile.name),
                deadline_hint=dict(profile.deadline_hint) if profile.deadline_hint else None,
                items=items,
                extra_items=extras,
                route=_route(index, profile, route, project, facts, tracer),
            )
        )
    return tuple(points)
