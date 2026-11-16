"""«Почему?» одного элемента результата: цепочка решений, соседи по правилам и «что если» (раздел 4.6 дизайна).

Чистые функции над готовым `Outcome` (с трассой). Расчёт соседних комбинаций вводных делает вызывающий (`resolve` лежит
в `use_cases`), сюда он приходит как `Neighbor`: одна вводная, одно другое её значение и состояния всех элементов
результата при нём.

- **Цепочка** это решения элемента из его `why`, в порядке `why`: от первого правила к последнему, у каждого условия,
  фактические значения и исход (`held`, `not_held`, `skipped`). У шага маршрута своего `why` нет: цепочка шага это
  порядок маршрута и решения пар, в которых участвуют люди шага.
- **Соседи** (`readers`) это другие элементы, о которых говорят решения цепочки: правило склеивается по содержимому,
  поэтому одно решение («порядок подписей версии», «вид работы: проектный» у одинаковых условий) бывает сразу у многих.
- **«Что если»** это минимальные изменения вводных: одна вводная в другое значение, при которой состояние элемента
  меняется. Первыми идут вводные невыполненных условий цепочки (они держат элемент выключенным), затем остальные
  вводные цепочки, затем прочие.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from hse_doc_studio.core.pack_studio.outcome.model import ElementRef, Outcome, TraceEntry
from hse_doc_studio.core.pack_studio.outcome.points import pair_id, step_id
from hse_doc_studio.core.pack_studio.outcome.trace import why

type ElementKey = tuple[str, str]

# Состояния элемента: у документа `active`, `inactive`, `absent`; у остальных `present` или `absent`.
PRESENT = "present"
ABSENT = "absent"

# Сколько записей отдаёт ответ (пределы модели контракта `PackOutcomeExplainResponse`).
MAX_READERS = 64
MAX_COUNTERFACTUALS = 24


@dataclass(frozen=True, slots=True)
class ElementInfo:
    """Элемент результата: его состояние и решения, из которых оно вышло."""

    state: str
    why: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Neighbor:
    """Соседняя комбинация: `input` поставлена в `value`, остальное как у результата. `states` это состояние каждого
    элемента при ней; элемента, которого в соседнем результате нет, нет и в словаре (он `absent`)."""

    input: str
    value: str
    states: Mapping[ElementKey, str]


@dataclass(frozen=True, slots=True)
class Counterfactual:
    input: str
    value: str
    result: str


@dataclass(frozen=True, slots=True)
class Explanation:
    element: ElementRef
    state: str
    chain: tuple[TraceEntry, ...]
    readers: tuple[ElementRef, ...]
    counterfactuals: tuple[Counterfactual, ...]


def _flag(present: bool) -> str:
    return PRESENT if present else ABSENT


def _route_elements(outcome: Outcome) -> dict[ElementKey, ElementInfo]:
    found: dict[ElementKey, ElementInfo] = {}
    for point in outcome.points:
        route = point.route
        found[("route", point.id)] = ElementInfo(PRESENT, route.why)
        for number, step in enumerate(route.steps, start=1):
            personas = {person.persona for person in step}
            reasons = why(*route.why, *(i for pair in route.pairs if pair.persona in personas for i in pair.why))
            found[("route", step_id(point.id, number))] = ElementInfo(PRESENT, reasons)
        for pair in route.pairs:
            found[("route", pair_id(point.id, pair.doc_id, pair.slot_id, pair.persona))] = ElementInfo(
                PRESENT, pair.why
            )
        for skipped in route.skipped:
            # Слот, которого в маршруте нет: он `absent`, а условие `when` в цепочке говорит почему. Пара с тем же id
            # (персона равна слоту) важнее: она в маршруте.
            found.setdefault(
                ("route", f"{point.id}/{skipped.doc_id}/{skipped.slot_id}"), ElementInfo(ABSENT, skipped.why)
            )
    return found


def _form_elements(outcome: Outcome) -> dict[ElementKey, ElementInfo]:
    found: dict[ElementKey, ElementInfo] = {}
    for form in outcome.forms:
        found[("forms", form.id)] = ElementInfo(_flag(form.applies), form.why)
        for form_field in form.fields:
            found[("forms", f"{form.id}/{form_field.id}")] = ElementInfo(_flag(form_field.visible), form_field.why)
    return found


def _point_elements(outcome: Outcome) -> dict[ElementKey, ElementInfo]:
    found: dict[ElementKey, ElementInfo] = {}
    for point in outcome.points:
        found[("points", point.id)] = ElementInfo(PRESENT, point.why)
        for item in point.items:
            found[("points", f"{point.id}/{item.doc_id}")] = ElementInfo(_flag(item.active), item.why)
        for extra in point.extra_items:
            found[("points", f"{point.id}/{extra.source}")] = ElementInfo(_flag(extra.active), extra.why)
    return found


def element_infos(outcome: Outcome) -> dict[ElementKey, ElementInfo]:
    """Все элементы результата по ключу (раздел, id) с состоянием и `why`. Идентификаторы по разделу 4.3 дизайна:
    документ `id`, поле `id`, анкета `id` и поле анкеты `<анкета>/<поле>`, участник `persona`, точка `id`, пункт
    `<точка>/<документ>`, шаг маршрута `<точка>/step/<номер>`, пара `<точка>/<документ>/<слот>`, правило проверки `id`;
    маршрут целиком под `route` и id точки."""
    found: dict[ElementKey, ElementInfo] = {}
    found.update({("documents", doc.id): ElementInfo(doc.state, doc.why) for doc in outcome.documents})
    found.update({("meta", f.id): ElementInfo(_flag(f.visible), f.why) for f in outcome.meta})
    found.update(_form_elements(outcome))
    found.update({("participants", p.persona): ElementInfo(_flag(p.present), p.why) for p in outcome.participants})
    found.update(_point_elements(outcome))
    found.update(_route_elements(outcome))
    found.update({("checks", c.id): ElementInfo(_flag(c.enabled), c.why) for c in outcome.checks or ()})
    return found


def element_states(outcome: Outcome) -> dict[ElementKey, str]:
    """Состояния всех элементов результата: то, что сравнивают «что если»."""
    return {key: info.state for key, info in element_infos(outcome).items()}


def _input_of(subject: str, known: Collection[str]) -> str | None:
    """Вводная, на которую указывает предмет условия: сама (`meta.manuals`) или та, чьё свойство читают
    (`supervisor.role` это вводная `supervisor`)."""
    name = subject
    while name:
        if name in known:
            return name
        name = name.rpartition(".")[0]
    return None


def inputs_of_entry(entry: TraceEntry, known: Collection[str]) -> tuple[str, ...]:
    """Вводные, которые читает решение (по предметам условий и фактическим значениям), без повторов."""
    subjects = [*(term.subject for term in entry.terms), *entry.actual]
    return tuple(dict.fromkeys(found for s in subjects if (found := _input_of(s, known)) is not None))


def referenced_inputs(trace: Iterable[TraceEntry], known: Collection[str]) -> frozenset[str]:
    """Вводные, которые читает хотя бы одно решение трассы: их соседей считают первыми."""
    return frozenset(name for entry in trace for name in inputs_of_entry(entry, known))


def _readers(chain: tuple[TraceEntry, ...], own: ElementRef) -> tuple[ElementRef, ...]:
    others = dict.fromkeys(subject for entry in chain for subject in entry.subjects if subject != own)
    return tuple(others)[:MAX_READERS]


def _counterfactuals(
    outcome: Outcome,
    key: ElementKey,
    state: str,
    chain: tuple[TraceEntry, ...],
    neighbors: Iterable[Neighbor],
) -> tuple[Counterfactual, ...]:
    known = set(outcome.inputs)
    blocking = {name for entry in chain if entry.status == "not_held" for name in inputs_of_entry(entry, known)}
    read = {name for entry in chain for name in inputs_of_entry(entry, known)}

    def rank(name: str) -> int:
        if name in blocking:
            return 0
        return 1 if name in read else 2

    changed = [
        Counterfactual(n.input, n.value, result) for n in neighbors if (result := n.states.get(key, ABSENT)) != state
    ]
    # Сортировка устойчива: внутри ранга порядок вводных и значений остаётся как у вызывающего.
    changed.sort(key=lambda c: rank(c.input))
    return tuple(changed[:MAX_COUNTERFACTUALS])


def find_element(outcome: Outcome, element: ElementRef) -> ElementInfo | None:
    """Состояние и `why` элемента; None: такого элемента в результате нет."""
    return element_infos(outcome).get((element.section, element.id))


def explain_element(outcome: Outcome, element: ElementRef, neighbors: Iterable[Neighbor]) -> Explanation | None:
    """Цепочка, соседи и «что если» элемента; None, если элемента в результате нет."""
    info = find_element(outcome, element)
    if info is None:
        return None
    by_id = {entry.id: entry for entry in outcome.trace}
    chain = tuple(by_id[i] for i in info.why if i in by_id)
    key: ElementKey = (element.section, element.id)
    return Explanation(
        element=element,
        state=info.state,
        chain=chain,
        readers=_readers(chain, element),
        counterfactuals=_counterfactuals(outcome, key, info.state, chain, neighbors),
    )


__all__ = [
    "ABSENT",
    "MAX_COUNTERFACTUALS",
    "MAX_READERS",
    "PRESENT",
    "Counterfactual",
    "ElementInfo",
    "ElementKey",
    "Explanation",
    "Neighbor",
    "element_infos",
    "element_states",
    "explain_element",
    "find_element",
    "inputs_of_entry",
    "referenced_inputs",
]
