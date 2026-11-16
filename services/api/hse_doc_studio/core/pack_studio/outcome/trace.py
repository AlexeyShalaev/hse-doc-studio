"""Трасса решений: плоский список правил с фактическими значениями и исходом (раздел 2.3 дизайна результата).

Каждое решение знает правило (файл и JSON Pointer манифеста либо имя зашитого правила), условия закрытого языка,
фактические значения вводных и исход (`held`, `not_held`, `skipped`). Одинаковые решения склеиваются: правило
«вид работы: проектный» одного документа остаётся одним решением, а элементы, о которых оно, копятся в `subjects`.
Элементы результата ссылаются на решения полем `why`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from hse_doc_studio.core.pack_studio.outcome.model import ElementRef, RuleRef, Term, TraceEntry, VerdictName


@dataclass(slots=True)
class _Draft:
    id: str
    rule: RuleRef
    kind: str
    effect: str
    join: str
    terms: tuple[Term, ...]
    actual: dict[str, str]
    status: VerdictName
    subjects: list[ElementRef] = field(default_factory=list)


@dataclass(slots=True)
class Tracer:
    """Копит решения. С `enabled=False` ничего не хранит и отдаёт пустые id: нужен расчёту без объяснений (атлас)."""

    enabled: bool = True
    _drafts: list[_Draft] = field(default_factory=list)
    _index: dict[tuple[object, ...], _Draft] = field(default_factory=dict)

    def decide(  # noqa: PLR0913 — решение целиком
        self,
        *,
        rule: RuleRef,
        kind: str,
        effect: str,
        terms: Iterable[Term],
        actual: Mapping[str, str],
        status: VerdictName,
        subjects: Iterable[ElementRef],
        join: str = "all",
    ) -> str:
        """Записать решение и вернуть его id (`t1`, `t2`, ...); пустая строка, если трасса выключена."""
        if not self.enabled:
            return ""
        term_tuple = tuple(terms)
        key = (rule, kind, effect, join, term_tuple, tuple(actual.items()), status)
        draft = self._index.get(key)
        if draft is None:
            draft = _Draft(
                id=f"t{len(self._drafts) + 1}",
                rule=rule,
                kind=kind,
                effect=effect,
                join=join,
                terms=term_tuple,
                actual=dict(actual),
                status=status,
            )
            self._drafts.append(draft)
            self._index[key] = draft
        for subject in subjects:
            if subject not in draft.subjects:
                draft.subjects.append(subject)
        return draft.id

    def status_of(self, decision_id: str) -> VerdictName | None:
        """Исход записанного решения; None: такого решения нет (или трасса выключена)."""
        for draft in self._drafts:
            if draft.id == decision_id:
                return draft.status
        return None

    def entries(self) -> tuple[TraceEntry, ...]:
        return tuple(
            TraceEntry(
                id=d.id,
                rule=d.rule,
                kind=d.kind,
                effect=d.effect,  # type: ignore[arg-type]
                join=d.join,  # type: ignore[arg-type]
                terms=d.terms,
                actual=d.actual,
                status=d.status,
                subjects=tuple(d.subjects),
            )
            for d in self._drafts
        )


def why(*ids: str) -> tuple[str, ...]:
    """Список `why` элемента: id решений без пустых (выключенная трасса) и повторов, порядок сохранён."""
    return tuple(dict.fromkeys(i for i in ids if i))


def manifest_rule(file: str, pointer: str) -> RuleRef:
    return RuleRef(origin="manifest", file=file, pointer=pointer)


def builtin_rule(name: str) -> RuleRef:
    return RuleRef(origin="builtin", builtin=name)
