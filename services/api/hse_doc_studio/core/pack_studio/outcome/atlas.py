"""Атлас результата: чистое ядро (раздел 4.4 дизайна результата, срез O4).

Атлас это таблица исходов по комбинациям вводных, которые реально меняют результат. Здесь живёт всё, что не
вызывает вычислитель: снимок результата для сравнения комбинаций, накопитель влияния вводной (разделы и элементы),
модель атласа, ключ строки и сборка таблицы с группами одинаковых исходов. Сам расчёт (перебор комбинаций через
`resolve`) в `use_cases/pack_studio/outcome/atlas.py`: `core` его не видит.

Влияние вводной считается по отпечаткам разделов (`summary.py`): вводная влияет на раздел, если у какого-то значения
других вводных смена её значения меняет отпечаток раздела. Если отпечатки не меняются, но меняется косметика документов
(имена файлов, языковая редакция, доступность и выбор варианта), вводная косметическая (R12): атлас её не включает.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from hse_doc_studio.core.pack_studio.outcome.model import SECTIONS, Digest, RuleRef, SectionName, Term, TraceEntry
from hse_doc_studio.core.pack_studio.outcome.summary import outcome_elements

if TYPE_CHECKING:
    from hse_doc_studio.core.pack_studio.outcome.model import Outcome

# Верхний предел таблицы атласа: больше строк это `atlas_too_large` (раздел 4.4).
ATLAS_MAX_ROWS = 2000
# Правил в измерении не больше, чем в схеме контракта (`AtlasDimension.rules`).
MAX_DIMENSION_RULES = 32
KEY_SEPARATOR = "|"
_KEY_ESCAPE = "%7C"

type IgnoredReason = Literal["no_effect", "cosmetic"]
# Элемент результата для влияния: раздел, вид (`document`, `route_step`, ...) и id по контракту.
type ElementKey = tuple[SectionName, str, str]


class AtlasTooLarge(Exception):  # noqa: N818 — доменное исключение, на границе `atlas_too_large`
    """Таблица длиннее предела: на границе `atlas_too_large` с полями `limit` и `rows`."""

    def __init__(self, rows: int, limit: int) -> None:
        super().__init__(f"atlas has {rows} rows, the limit is {limit}")
        self.rows = rows
        self.limit = limit


class AtlasCancelled(Exception):  # noqa: N818 — расчёт остановлен по сроку, на границе 503 с `Retry-After`
    """Расчёт остановлен вызывающим (истёк срок): частичный результат не нужен."""


# ── Снимок результата и влияние вводной ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Что нужно знать о результате комбинации, чтобы сравнивать комбинации между собой.

    `prints` отпечатки разделов в порядке `SECTIONS`; `elements` по разделам: (вид, id) элемента и хэш его структуры;
    `cosmetic` хэш косметики документов (имена файлов, редакция, варианты). Самого результата снимок не держит: на
    5184 комбинации ВКР результат занял бы сотни мегабайт."""

    fingerprint: str
    prints: tuple[str, ...]
    elements: tuple[dict[tuple[str, str], int], ...]
    cosmetic: int


def snapshot_of(outcome: Outcome) -> Snapshot:
    """Снимок готового результата (разделы берутся из `digest`, элементы из индекса `outcome_elements`)."""
    by_section = outcome_elements(outcome)
    prints = {p.section: p.fingerprint for p in outcome.digest.sections}
    return Snapshot(
        fingerprint=outcome.fingerprint,
        prints=tuple(prints[s] for s in SECTIONS),
        elements=tuple(
            {(e.kind, e.id): hash(repr(e.structure)) for e in by_section[s]} if s != "checks" else {} for s in SECTIONS
        ),
        cosmetic=hash(repr([(e.id, e.cosmetic) for e in by_section["documents"]])),
    )


@dataclass(frozen=True, slots=True)
class InputImpact:
    """Что меняет вводная: разделы и элементы результата (точно по перебору либо по соседним комбинациям).

    `cosmetic`: структура не меняется, меняются только имена файлов, редакция и варианты документов."""

    input: str
    sections: tuple[SectionName, ...]
    elements: tuple[ElementKey, ...]
    cosmetic: bool

    @property
    def effective(self) -> bool:
        return bool(self.sections)

    @property
    def ignored_reason(self) -> IgnoredReason | None:
        """Почему вводной нет в измерениях атласа; None у измерения."""
        if self.effective:
            return None
        return "cosmetic" if self.cosmetic else "no_effect"


@dataclass(slots=True)
class ImpactAccumulator:
    """Копит различия значений одной вводной по группам комбинаций, в которых другие вводные одинаковы."""

    input: str
    sections: set[SectionName] = field(default_factory=set)
    elements: set[ElementKey] = field(default_factory=set)
    cosmetic: bool = False

    def compare(self, left: Snapshot, right: Snapshot) -> None:
        """Сравнить два результата, где различается только эта вводная."""
        if left is right:
            return
        for index, section in enumerate(SECTIONS):
            if left.prints[index] == right.prints[index]:
                continue
            self.sections.add(section)
            before, after = left.elements[index], right.elements[index]
            # Симметрическая разность пар (элемент, хэш): C-скорость, а ключи нужны только у различающихся.
            for kind, element_id in {key for key, _ in before.items() ^ after.items()}:
                self.elements.add((section, kind, element_id))
        if left.cosmetic != right.cosmetic:
            self.cosmetic = True

    def result(self) -> InputImpact:
        order = {s: i for i, s in enumerate(SECTIONS)}
        return InputImpact(
            input=self.input,
            sections=tuple(sorted(self.sections, key=order.__getitem__)),
            elements=tuple(sorted(self.elements, key=lambda e: (order[e[0]], e[1], e[2]))),
            cosmetic=self.cosmetic and not self.sections,
        )


# ── Правила, которые читают вводную ──────────────────────────────────────────


def term_reads(term: Term, input_id: str) -> bool:
    """Условие читает вводную: на ней самой или на её части (`supervisor.role`)."""
    return term.subject == input_id or term.subject.startswith(f"{input_id}.")


def reading_rules(trace: Iterable[TraceEntry], input_id: str) -> list[RuleRef]:
    """Правила, у которых есть условие на вводной, в порядке трассы и без повторов (одно правило может решать
    несколько элементов, но правило одно)."""
    seen: dict[RuleRef, None] = {}
    for entry in trace:
        if any(term_reads(term, input_id) for term in entry.terms):
            seen.setdefault(entry.rule)
    return list(seen)


# ── Модель атласа ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AtlasDimension:
    """Измерение: вводная, которая меняет хотя бы один раздел. У закреплённой (`pin`) одно значение."""

    input: str
    values: tuple[str, ...]
    default: str
    affects: tuple[SectionName, ...]
    rules: tuple[RuleRef, ...]


@dataclass(frozen=True, slots=True)
class AtlasIgnored:
    input: str
    reason: IgnoredReason


@dataclass(frozen=True, slots=True)
class AtlasOutcome:
    """Исход: уникальный отпечаток результата, его `digest` и сколько строк таблицы его дают."""

    id: str
    fingerprint: str
    digest: Digest
    rows: int


@dataclass(frozen=True, slots=True)
class AtlasRow:
    key: str
    outcome: str


@dataclass(frozen=True, slots=True)
class Atlas:
    """Таблица исходов (поля границы запроса и `elapsed_ms` добавляет вызывающий)."""

    revision: str
    dimensions: tuple[AtlasDimension, ...]
    ignored: tuple[AtlasIgnored, ...]
    # Полный перебор всех вводных и таблица после отбрасывания неважных и закреплённых.
    combinations_total: int
    rows_total: int
    outcomes_distinct: int
    outcomes: tuple[AtlasOutcome, ...]
    rows: tuple[AtlasRow, ...]
    elapsed_ms: int = 0

    def distinct_by(self, sections: Iterable[SectionName]) -> int:
        """Сколько различных исходов, если смотреть только на эти разделы (счётчик «24 исхода без участников»)."""
        wanted = frozenset(sections)
        return len({tuple(p.fingerprint for p in o.digest.sections if p.section in wanted) for o in self.outcomes})


# ── Ключ и сборка таблицы ────────────────────────────────────────────────────


def encode_key(values: Iterable[str]) -> str:
    """Ключ строки: значения измерений по порядку через `|`; `|` внутри значения пишется `%7C`."""
    return KEY_SEPARATOR.join(value.replace(KEY_SEPARATOR, _KEY_ESCAPE) for value in values)


def decode_key(key: str) -> tuple[str, ...]:
    """Значения измерений из ключа строки (обратное `encode_key`)."""
    return tuple(part.replace(_KEY_ESCAPE, KEY_SEPARATOR) for part in key.split(KEY_SEPARATOR))


def row_count(dimensions: Sequence[tuple[str, Sequence[str]]]) -> int:
    """Строк в таблице: произведение чисел значений измерений (без измерений одна строка)."""
    count = 1
    for _, values in dimensions:
        count *= len(values)
    return count


def combinations_count(value_counts: Iterable[int]) -> int:
    """Размер полного перебора всех вводных."""
    total = 1
    for count in value_counts:
        total *= count
    return total


def assemble_table(
    dimensions: Sequence[tuple[str, Sequence[str]]],
    evaluate: Callable[[Mapping[str, str]], tuple[str, Digest]],
    *,
    limit: int = ATLAS_MAX_ROWS,
    check: Callable[[], None] | None = None,
) -> tuple[tuple[AtlasOutcome, ...], tuple[AtlasRow, ...]]:
    """Таблица исходов: строка на каждую комбинацию значений измерений, одинаковые исходы собраны в группы.

    `evaluate` по значениям измерений (остальные вводные вызывающий держит на умолчаниях) возвращает отпечаток и
    `digest` результата. Исходы нумеруются `o1`, `o2`... в порядке первого появления; `digest` берётся из первой
    строки группы (у строк группы он один: отпечаток структуры без косметики). Больше `limit` строк это
    `AtlasTooLarge` до расчёта. `check` вызывается на каждой строке: вызывающий останавливает расчёт по сроку."""
    total = row_count(dimensions)
    if total > limit:
        raise AtlasTooLarge(total, limit)
    ids: dict[str, str] = {}
    digests: dict[str, Digest] = {}
    counts: Counter[str] = Counter()
    rows: list[AtlasRow] = []
    names = [name for name, _ in dimensions]
    for values in itertools.product(*(vals for _, vals in dimensions)):
        if check is not None:
            check()
        fingerprint, digest = evaluate(dict(zip(names, values, strict=True)))
        if fingerprint not in ids:
            ids[fingerprint] = f"o{len(ids) + 1}"
            digests[fingerprint] = digest
        counts[fingerprint] += 1
        rows.append(AtlasRow(encode_key(values), ids[fingerprint]))
    outcomes = tuple(AtlasOutcome(ids[fp], fp, digests[fp], counts[fp]) for fp in ids)
    return outcomes, tuple(rows)
