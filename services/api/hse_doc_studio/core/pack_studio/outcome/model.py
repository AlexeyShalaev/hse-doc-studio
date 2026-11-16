"""Модель результата вычислителя: те же поля, что у контракта (`api/schemas/pack_studio_outcome.py`), без pydantic.

Слой core не знает про api, поэтому форма дублируется данными, а `payload.outcome_to_json` превращает результат в
словарь, который строгие модели контракта принимают как есть (это проверяет тест паритета с эталонами).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

type Localized = dict[str, str]

SectionName = Literal["documents", "meta", "forms", "participants", "points", "route", "checks"]
SECTIONS: tuple[SectionName, ...] = ("documents", "meta", "forms", "participants", "points", "route", "checks")
DocumentStateName = Literal["active", "inactive", "absent"]
ItemOffReason = Literal["nda", "kind", "absent", "inactive"]
CheckOffReason = Literal["disabled", "category_disabled", "no_active_document"]
OrderSourceName = Literal["profile", "version", "builtin"]
IncludeName = Literal["branches", "checks"]
VerdictName = Literal["held", "not_held", "skipped"]
OutOfScopeName = Literal["python_checks", "signature_anchors", "tex_content", "jinja_content"]

# Что в результат не входит (раздел 8): правила проверок на Python, места подписей по якорям PDF, TeX и Jinja.
OUT_OF_SCOPE: tuple[OutOfScopeName, ...] = ("python_checks", "signature_anchors", "tex_content", "jinja_content")


@dataclass(frozen=True, slots=True)
class ElementRef:
    """Элемент результата: раздел и id (у вложенных через косую черту: `final/report/supervisor`)."""

    section: SectionName
    id: str


@dataclass(frozen=True, slots=True)
class RuleRef:
    """Где лежит правило: файл от каталога версии и путь JSON Pointer либо имя зашитого в движок правила."""

    origin: Literal["manifest", "builtin"]
    file: str | None = None
    pointer: str | None = None
    builtin: str | None = None


@dataclass(frozen=True, slots=True)
class Term:
    """Одно условие закрытого языка: `in`, `equals`, `contains_any`, `present`, `truthy`."""

    op: Literal["in", "equals", "contains_any", "present", "truthy"]
    subject: str
    expected: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TraceEntry:
    """Одно решение вычислителя: правило, условия, фактические значения, исход и элементы, о которых оно."""

    id: str
    rule: RuleRef
    kind: str
    effect: Literal["gate", "exclude", "add", "order", "display", "require"]
    join: Literal["all", "any"]
    terms: tuple[Term, ...]
    actual: dict[str, str]
    status: VerdictName
    subjects: tuple[ElementRef, ...]


@dataclass(frozen=True, slots=True)
class VariantOption:
    id: str
    label: Localized
    # Языки проекта, в которых вариант доступен; пусто: во всех.
    langs: tuple[str, ...]
    available: bool
    chosen: bool
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Instance:
    id: str
    owner: str | None
    owner_name: str | None
    file_name: str | None


@dataclass(frozen=True, slots=True)
class DocumentOutcome:
    id: str
    name: Localized
    group: str | None
    scope: Literal["shared", "personal"]
    required: bool
    state: DocumentStateName
    lang_state: Literal["native", "fallback"]
    languages: tuple[str, ...]
    variants: tuple[VariantOption, ...]
    instances: tuple[Instance, ...]
    source_file: str | None
    manifest: str
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetaOutcome:
    id: str
    type: str
    label: Localized
    scope: str
    group: str | None
    visible: bool
    required_at: str
    value: str | None
    options: tuple[str, ...]
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FormFieldOutcome:
    id: str
    type: str
    label: Localized
    visible: bool
    required: bool
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FormOutcome:
    id: str
    title: Localized
    per_author: bool
    applies: bool
    required_for_pack: bool
    fields: tuple[FormFieldOutcome, ...]
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParticipantOutcome:
    persona: str
    role: Literal["author", "supervisor", "co_supervisor", "academic_supervisor"]
    name: str
    present: bool
    org: Literal["university", "company"] | None
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PointItem:
    doc_id: str
    active: bool
    off_reason: ItemOffReason | None
    signatures: tuple[str, ...]
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PointExtra:
    source: str
    output_name: str
    format: str | None
    active: bool
    off_reason: ItemOffReason | None
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RoutePerson:
    persona: str
    role: Literal["author", "supervisor", "co_supervisor", "academic_supervisor"]
    name: str


@dataclass(frozen=True, slots=True)
class When:
    person: str
    role: str | None = None


@dataclass(frozen=True, slots=True)
class RoutePair:
    doc_id: str
    slot_id: str
    persona: str
    source: Literal["point", "preset"]
    optional: bool
    when: When | None
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkippedPair:
    doc_id: str
    slot_id: str
    when: When | None
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocSlot:
    doc_id: str
    slot_id: str


@dataclass(frozen=True, slots=True)
class RouteOutcome:
    steps: tuple[tuple[RoutePerson, ...], ...]
    pairs: tuple[RoutePair, ...]
    skipped: tuple[SkippedPair, ...]
    may_add: tuple[DocSlot, ...]
    order_source: OrderSourceName
    preset: bool
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PointOutcome:
    id: str
    index: int
    name: Localized
    deadline_hint: Localized | None
    items: tuple[PointItem, ...]
    extra_items: tuple[PointExtra, ...]
    route: RouteOutcome
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckRuleOutcome:
    id: str
    title: Localized
    category: str | None
    severity: Literal["info", "warn", "err"]
    engine: str
    enabled: bool
    off_reason: CheckOffReason | None
    applies_to: tuple[str, ...]
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChangeReason:
    """Правило, из-за которого элемент изменился при сравнении двух результатов: исход решения слева (`before`) и справа
    (`after`; None: у этого элемента решения на этой стороне нет) и фактические значения вводных с каждой стороны."""

    rule: RuleRef
    kind: str
    terms: tuple[Term, ...]
    before: VerdictName | None
    after: VerdictName | None
    before_actual: dict[str, str]
    after_actual: dict[str, str]


@dataclass(frozen=True, slots=True)
class SectionDelta:
    section: SectionName
    added: int
    changed: int
    removed: int


@dataclass(frozen=True, slots=True)
class Alternative:
    value: str
    label: Localized | None
    fingerprint: str
    # Что изменится в результате, если выбрать это значение; пусто у текущего.
    delta: tuple[SectionDelta, ...]


@dataclass(frozen=True, slots=True)
class Branch:
    input: str
    label: Localized | None
    chosen: str
    affects: tuple[SectionName, ...]
    alternatives: tuple[Alternative, ...]


@dataclass(frozen=True, slots=True)
class SectionPrint:
    section: SectionName
    fingerprint: str
    count: int


@dataclass(frozen=True, slots=True)
class DigestPoint:
    id: str
    items: tuple[str, ...]
    steps: tuple[tuple[str, ...], ...]
    pairs: int


@dataclass(frozen=True, slots=True)
class Digest:
    documents: dict[str, DocumentStateName]
    participants: tuple[str, ...]
    meta_visible: tuple[str, ...]
    points: tuple[DigestPoint, ...]
    sections: tuple[SectionPrint, ...]


@dataclass(frozen=True, slots=True)
class Outcome:
    """Результат вычислителя. Поля границы запроса (пространство, пак, состояние) и `elapsed_ms` добавляет вызывающий:
    функция чистая, часов не читает."""

    revision: str
    inputs: dict[str, str]
    example: str
    fingerprint: str
    documents: tuple[DocumentOutcome, ...]
    meta: tuple[MetaOutcome, ...]
    forms: tuple[FormOutcome, ...]
    participants: tuple[ParticipantOutcome, ...]
    points: tuple[PointOutcome, ...]
    checks: tuple[CheckRuleOutcome, ...] | None
    branches: tuple[Branch, ...] | None
    digest: Digest
    trace: tuple[TraceEntry, ...]
    out_of_scope: tuple[OutOfScopeName, ...] = field(default=OUT_OF_SCOPE)
    elapsed_ms: int = 0


# ── Словарь вводных версии (список для панели) ───────────────────────────────


@dataclass(frozen=True, slots=True)
class InputValueInfo:
    value: str
    label: Localized | None


@dataclass(frozen=True, slots=True)
class InputInfo:
    """Вводная панели. `affects` это разделы, которые меняются при смене вводной (по соседним комбинациям, атлас
    уточняет по всем), `rules` сколько решений трассы на умолчаниях читают эту вводную."""

    id: str
    group: Literal["project", "people", "meta", "answers", "variants"]
    type: Literal["select", "bool"]
    label: Localized | None
    values: tuple[InputValueInfo, ...]
    default: str
    affects: tuple[SectionName, ...]
    rules: int


@dataclass(frozen=True, slots=True)
class InputsDictionary:
    revision: str
    inputs: tuple[InputInfo, ...]
    defaults: dict[str, str]
