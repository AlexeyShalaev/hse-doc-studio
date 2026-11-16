"""Правила линтера результата по атласу (раздел 6.1 дизайна, срез O8).

`AtlasObserver` смотрит на результат каждой строки атласа (результат с трассой) и копит то, что нужно правилам и
покрытию: исходы правил (`held`, `not_held`, `skipped`) с первой строкой, где виден каждый, активные документы и
пункты, видимые поля, маршруты. Сам перебор строк делает вызывающий (`use_cases/pack_studio/outcome/lint.py`): здесь
чистая свёртка, ни расчёта, ни часов.

`finish()` превращает накопленное в находки и в универсум покрытия (`coverage.RuleUniverse`). У находки до трёх строк
атласа (`witnesses`), на которых она видна: значения измерений, их можно закрепить (`pin`) или поставить на экране.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from hse_doc_studio.core.catalog import SubmissionProfile, TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.coverage import OUTCOMES, RuleUniverse, UniverseRule
from hse_doc_studio.core.pack_studio.outcome.lint import (
    MAX_WITNESSES,
    VERSION_MANIFEST,
    LintFinding,
    Witness,
    doc_manifest,
    finding,
)
from hse_doc_studio.core.pack_studio.outcome.lint_static import named_slots, slot_never_routed
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef, Outcome, PointOutcome, RuleRef
from hse_doc_studio.core.pack_studio.outcome.people import steps_without_person

type RowKey = tuple[str, ...]


@dataclass(slots=True)
class _RuleStat:
    kind: str
    seen: dict[str, Witness] = field(default_factory=dict)
    subjects: dict[ElementRef, None] = field(default_factory=dict)

    def add(self, status: str, row: Witness, subjects: Iterable[ElementRef]) -> None:
        self.seen.setdefault(status, row)
        for subject in subjects:
            if len(self.subjects) < MAX_WITNESSES * 4:
                self.subjects.setdefault(subject)


@dataclass(slots=True)
class _Witnesses:
    """Первые строки атласа, где что-то случилось (до `MAX_WITNESSES`), и сколько всего."""

    rows: list[Witness] = field(default_factory=list)
    count: int = 0

    def add(self, row: Witness) -> None:
        self.count += 1
        if len(self.rows) < MAX_WITNESSES:
            self.rows.append(row)


@dataclass(frozen=True, slots=True)
class AtlasObservation:
    """Итог обхода атласа: находки по атласу и универсум правил для покрытия."""

    findings: tuple[LintFinding, ...]
    universe: RuleUniverse


class AtlasObserver:
    def __init__(self, version: TemplateVersion, dimensions: Sequence[str]) -> None:
        self._version = version
        self._dimensions = tuple(dimensions)
        self._rows: list[RowKey] = []
        self._cells: list[frozenset[int]] = []
        self._rules: dict[RuleRef, _RuleStat] = {}
        self._rule_index: dict[RuleRef, int] = {}
        self._docs_active: set[str] = set()
        self._items_active: set[tuple[str, str]] = set()
        self._slots_routed: set[str] = set()
        self._meta_visible: set[str] = set()
        self._fields_visible: set[tuple[str, str]] = set()
        self._step_gaps: dict[tuple[str, str], _Witnesses] = defaultdict(_Witnesses)
        self._route_gaps: dict[str, _Witnesses] = defaultdict(_Witnesses)
        self._empty_points: dict[str, _Witnesses] = defaultdict(_Witnesses)
        self._overlaps: dict[tuple[int, int], _Witnesses] = defaultdict(_Witnesses)
        self._order_source: dict[str, str] = {}

    # ── обход ────────────────────────────────────────────────────────────────

    def observe(self, values: RowKey, outcome: Outcome) -> None:
        """Одна строка атласа: значения измерений по порядку и её результат (с трассой)."""
        row = dict(zip(self._dimensions, values, strict=True))
        self._rows.append(values)
        self._cells.append(self._observe_trace(row, outcome))
        self._docs_active.update(doc.id for doc in outcome.documents if doc.state == "active")
        self._meta_visible.update(item.id for item in outcome.meta if item.visible)
        for form in outcome.forms:
            self._fields_visible.update((form.id, item.id) for item in form.fields if item.visible)
        for point in outcome.points:
            self._observe_point(row, outcome, point)

    def _observe_trace(self, row: Witness, outcome: Outcome) -> frozenset[int]:
        cells: set[int] = set()
        for entry in outcome.trace:
            stat = self._rules.setdefault(entry.rule, _RuleStat(entry.kind))
            stat.add(entry.status, row, entry.subjects)
            if entry.status != "skipped":
                index = self._rule_index.setdefault(entry.rule, len(self._rule_index))
                cells.add(index * 2 + OUTCOMES.index(entry.status))
        return frozenset(cells)

    def _observe_point(self, row: Witness, outcome: Outcome, point: PointOutcome) -> None:
        for item in point.items:
            if item.active:
                self._items_active.add((point.id, item.doc_id))
        self._slots_routed.update(pair.slot_id for pair in point.route.pairs)
        self._order_source.setdefault(point.id, point.route.order_source)
        if not any(item.active for item in point.items) and not any(extra.active for extra in point.extra_items):
            self._empty_points[point.id].add(row)
        for _number, persona in steps_without_person(point.route.steps, outcome.participants):
            self._step_gaps[(point.id, persona)].add(row)
        if self._route_gap(point, outcome):
            self._route_gaps[point.id].add(row)
        self._observe_overlap(row, outcome, point)

    @staticmethod
    def _route_gap(point: PointOutcome, outcome: Outcome) -> bool:
        """Точка требует подписей, а подписать некому: ни у одной пары нет человека в комбинации."""
        if not any(item.active and item.signatures for item in point.items):
            return False
        present = {p.persona for p in outcome.participants if p.present}
        return not any(pair.persona in present for pair in point.route.pairs)

    def _observe_overlap(self, row: Witness, outcome: Outcome, point: PointOutcome) -> None:
        profile = self._version.pack_submission.profiles[point.index]
        groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for k, entry in enumerate(profile.signing_slots):
            groups[(entry.doc_id, entry.slot_id)].append(k)
        people = {p.persona: p for p in outcome.participants if p.present}
        for ks in groups.values():
            held = [k for k in ks if _entry_held(profile, k, people)]
            whens = {_when_key(profile, k) for k in held}
            if len(held) > 1 and len(whens) > 1:
                self._overlaps[(point.index, held[1])].add(row)

    # ── итог ─────────────────────────────────────────────────────────────────

    def finish(self) -> AtlasObservation:
        found: list[LintFinding] = []
        for rule in (
            self._slot_findings,
            self._step_findings,
            self._gap_findings,
            self._document_findings,
            self._item_findings,
            self._empty_findings,
            self._field_findings,
            self._when_findings,
            self._overlap_findings,
        ):
            found.extend(rule())
        return AtlasObservation(tuple(found), self._universe())

    def _universe(self) -> RuleUniverse:
        rules: list[UniverseRule | None] = [None] * len(self._rule_index)
        for rule, index in self._rule_index.items():
            stat = self._rules[rule]
            possible = tuple(s for s in OUTCOMES if s in stat.seen)
            rules[index] = UniverseRule(rule, stat.kind, possible, {s: stat.seen[s] for s in possible})
        return RuleUniverse(
            rules=tuple(r for r in rules if r is not None),
            dimensions=self._dimensions,
            rows=tuple(self._rows),
            row_cells=tuple(self._cells),
        )

    def _slot_findings(self) -> Iterable[LintFinding]:
        named = named_slots(self._version)
        for index, slot in enumerate(self._version.signatures_config.slots):
            if slot.id not in self._slots_routed:
                yield slot_never_routed(slot.id, index, named=slot.id in named)

    def _step_findings(self) -> Iterable[LintFinding]:
        by_point: dict[str, dict[str, _Witnesses]] = defaultdict(dict)
        for (point_id, persona), witnesses in self._step_gaps.items():
            by_point[point_id][persona] = witnesses
        for index, profile in enumerate(self._version.pack_submission.profiles):
            personas = by_point.get(profile.id)
            if not personas:
                continue
            rows = [row for witnesses in personas.values() for row in witnesses.rows][:MAX_WITNESSES]
            count = max(w.count for w in personas.values())
            yield LintFinding(
                "route-step-without-person",
                "warning",
                f"Маршрут точки «{profile.id}» ждёт подписи от персон, которых нет в проекте: "
                f"{', '.join(sorted(personas))} (в {count} из {len(self._rows)} строк атласа). Шаг остаётся в "
                "маршруте, и закрыть его некому.",
                "Если персона обязательна, не допускайте проект без неё (вводная supervisor: none). Если нет, "
                "поставьте слот сверх точки с условием when, чтобы шаг появлялся только при наличии человека.",
                VERSION_MANIFEST,
                self._order_pointer(index, profile),
                None,
                (ElementRef("route", profile.id),),
                tuple(rows),
            )

    def _order_pointer(self, index: int, profile: SubmissionProfile) -> str:
        source = self._order_source.get(profile.id, "builtin")
        if source == "profile":
            return f"/pack_submission/profiles/{index}/signing_route"
        return "/signatures/route" if source == "version" else f"/pack_submission/profiles/{index}"

    def _gap_findings(self) -> Iterable[LintFinding]:
        for index, profile in enumerate(self._version.pack_submission.profiles):
            gaps = self._route_gaps.get(profile.id)
            if gaps is None:
                continue
            yield LintFinding(
                "route-gap",
                "warning",
                f"Точка «{profile.id}» требует подписей, но в {gaps.count} из {len(self._rows)} строк атласа "
                "подписать некому: ни одного человека маршрута нет в комбинации.",
                "Добавьте в точку подпись автора или слот сверх точки, который есть в таких проектах, либо не "
                "допускайте проект без руководителя.",
                VERSION_MANIFEST,
                f"/pack_submission/profiles/{index}",
                None,
                (ElementRef("route", profile.id),),
                tuple(gaps.rows),
            )

    def _document_findings(self) -> Iterable[LintFinding]:
        for doc in self._version.documents:
            if doc.id in self._docs_active:
                continue
            blockers = self._blockers(ElementRef("documents", doc.id))
            yield finding(
                "document-never-active",
                "warning",
                f"Документ «{doc.id}» не активен ни в одной комбинации вводных" + _because(blockers),
                "Проверьте supported_kinds и supported_staffing документа (их пересечение пусто?) и условия NDA и "
                "руководств, либо удалите документ из ростера.",
                doc_manifest(doc.id),
                blockers[0][1] if blockers else "/supported_kinds",
                ElementRef("documents", doc.id),
            )

    def _blockers(self, element: ElementRef) -> list[tuple[str, str]]:
        """Правила документа, которые ни в одной строке не выполняются: (название, указатель)."""
        found: list[tuple[str, str]] = []
        for rule, stat in self._rules.items():
            if element in stat.subjects and "held" not in stat.seen and "not_held" in stat.seen:
                pointer = rule.pointer or "/supported_kinds"
                found.append((rule.builtin or pointer.rsplit("/", 1)[-1], pointer))
        return found

    def _item_findings(self) -> Iterable[LintFinding]:
        for p_index, profile in enumerate(self._version.pack_submission.profiles):
            for i_index, item in enumerate(profile.items):
                if (profile.id, item.doc_id) in self._items_active or item.doc_id not in self._docs_active:
                    continue
                yield finding(
                    "item-never-active",
                    "warning",
                    f"Пункт «{item.doc_id}» точки «{profile.id}» не сдаётся ни в одной комбинации вводных, хотя "
                    "документ в комплекте бывает.",
                    "Проверьте supported_kinds и skip_if_nda пункта: вместе с условиями документа они не "
                    "оставляют ни одной комбинации.",
                    VERSION_MANIFEST,
                    f"/pack_submission/profiles/{p_index}/items/{i_index}",
                    ElementRef("points", f"{profile.id}/{item.doc_id}"),
                )

    def _empty_findings(self) -> Iterable[LintFinding]:
        for index, profile in enumerate(self._version.pack_submission.profiles):
            empty = self._empty_points.get(profile.id)
            if empty is None:
                continue
            where = "во всех комбинациях" if empty.count == len(self._rows) else f"в {empty.count} комбинациях"
            yield LintFinding(
                "point-empty",
                "info",
                f"Точка «{profile.id}» пуста {where} из {len(self._rows)} строк атласа: нет ни одного пункта.",
                "Это нормально, если точка нужна не всем видам работы. Иначе проверьте supported_kinds пунктов.",
                VERSION_MANIFEST,
                f"/pack_submission/profiles/{index}",
                None,
                (ElementRef("points", profile.id),),
                tuple(empty.rows),
            )

    def _field_findings(self) -> Iterable[LintFinding]:
        for key, meta in self._version.meta_fields.items():
            if key in self._meta_visible:
                continue
            required = meta.required_at.value != "never"
            yield _hidden_field(f"Поле проекта «{key}»", required, f"/meta_fields/{key}", ElementRef("meta", key))
        for f_index, form in enumerate(self._version.forms):
            for s_index, section in enumerate(form.sections):
                for i_index, item in enumerate(section.fields):
                    if item.type.value == "markdown" or (form.id, item.id) in self._fields_visible:
                        continue
                    base = f"/forms/{f_index}/sections/{s_index}/fields/{i_index}"
                    yield _hidden_field(
                        f"Поле «{item.id}» анкеты «{form.id}»",
                        item.required,
                        base,
                        ElementRef("forms", f"{form.id}/{item.id}"),
                    )

    def _when_findings(self) -> Iterable[LintFinding]:
        for p_index, profile in enumerate(self._version.pack_submission.profiles):
            for k, entry in enumerate(profile.signing_slots):
                if entry.when is None:
                    continue
                pointer = f"/pack_submission/profiles/{p_index}/signing_slots/{k}/when"
                stat = self._rules.get(RuleRef("manifest", VERSION_MANIFEST, pointer))
                yield from _when_finding(profile.id, entry.doc_id, entry.slot_id, pointer, stat)

    def _overlap_findings(self) -> Iterable[LintFinding]:
        for (p_index, k), witnesses in self._overlaps.items():
            profile = self._version.pack_submission.profiles[p_index]
            entry = profile.signing_slots[k]
            yield LintFinding(
                "slot-when-overlap",
                "warning",
                f"Точка «{profile.id}»: для слота «{entry.slot_id}» документа «{entry.doc_id}» две записи "
                f"signing_slots с разными условиями when выполняются вместе (в {witnesses.count} комбинациях): "
                "слот получит двух разных подписантов.",
                "Сделайте условия взаимоисключающими (разные роли руководителя) или оставьте одну запись.",
                VERSION_MANIFEST,
                f"/pack_submission/profiles/{p_index}/signing_slots/{k}",
                None,
                (ElementRef("route", f"{profile.id}/{entry.doc_id}/{entry.slot_id}"),),
                tuple(witnesses.rows),
            )


# ── Помощники ────────────────────────────────────────────────────────────────


def _because(blockers: Sequence[tuple[str, str]]) -> str:
    if not blockers:
        return "."
    return " (не выполняется условие: " + ", ".join(name for name, _ in blockers[:3]) + ")."


def _hidden_field(what: str, required: bool, pointer: str, element: ElementRef) -> LintFinding:
    if required:
        return finding(
            "required-hidden",
            "error",
            f"{what} обязательно, но скрыто в каждой комбинации вводных: заполнить его нельзя.",
            "Проверьте supported_kinds поля (анкеты) и visible_if: условие недостижимо. Либо снимите обязательность.",
            VERSION_MANIFEST,
            pointer,
            element,
        )
    return finding(
        "field-never-visible",
        "warning",
        f"{what} скрыто в каждой комбинации вводных: пользователь его не увидит.",
        "Проверьте supported_kinds поля (анкеты) и visible_if либо удалите поле.",
        VERSION_MANIFEST,
        pointer,
        element,
    )


def _when_finding(
    profile_id: str, doc_id: str, slot_id: str, pointer: str, stat: _RuleStat | None
) -> Iterable[LintFinding]:
    element = (ElementRef("route", f"{profile_id}/{doc_id}/{slot_id}"),)
    seen = stat.seen if stat is not None else {}
    if "held" not in seen:
        yield LintFinding(
            "when-never-held",
            "warning",
            f"Условие when слота «{slot_id}» документа «{doc_id}» (точка «{profile_id}») не выполняется ни в одной "
            "комбинации вводных: слот мёртвый.",
            "Проверьте person и role: такой человек в проектах бывает? Либо документ точки не бывает активным.",
            VERSION_MANIFEST,
            pointer,
            None,
            element,
            (seen["not_held"],) if "not_held" in seen else (),
        )
    elif "not_held" not in seen:
        yield LintFinding(
            "when-always-held",
            "info",
            f"Условие when слота «{slot_id}» документа «{doc_id}» (точка «{profile_id}») выполняется всегда: оно "
            "лишнее.",
            "Уберите when, если слот нужен всем, или сузьте условие.",
            VERSION_MANIFEST,
            pointer,
            None,
            element,
            (seen["held"],),
        )


def _entry_held(profile: SubmissionProfile, k: int, people: Mapping[str, object]) -> bool:
    """Условие записи `signing_slots` выполнено на людях комбинации (как `condition_met`: человек есть и роль)."""
    when = profile.signing_slots[k].when
    if when is None:
        return True
    person = people.get(when.person)
    if person is None:
        return False
    return when.role is None or getattr(person, "org", None) == when.role.value


def _when_key(profile: SubmissionProfile, k: int) -> tuple[str, str] | None:
    when = profile.signing_slots[k].when
    return None if when is None else (when.person, when.role.value if when.role is not None else "")
