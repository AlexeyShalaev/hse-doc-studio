"""`resolve`: результат версии шаблона для вводных (раздел 4.1 дизайна результата).

Чистая функция: файлов не читает, времени и случайности не берёт (`today` передаёт вызывающий), в сеть и базу не
ходит. Версию (`TemplateVersion`) и набор данных (`PreviewExample`) вызывающий уже разобрал, `revision` считает он же
по текстам манифестов (`core/pack_studio/outcome/revision.py`).

Порядок: вводные (умолчания версии, набор данных, запрос) -> синтетический проект (те же `synthetic_project` и
`synthetic_core_project`, что у предпросмотра, персоны авторов команды `author1..`) -> факты -> вычислители разделов
с общей трассой -> отпечатки и `digest`. Документы и маршруты берутся у движка (`_build_documents`, `is_doc_active`,
`profile_route`), трасса пишется рядом теми же предикатами (`core/pack_studio/outcome/predicates.py`).

Сборка (рендер Jinja и TeX) в расчёт не входит: она в `out_of_scope`. Ошибка расчёта, в том числе исключение движка,
поднимается к вызывающему, а не прячется.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import replace
from datetime import date

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.pack_studio.outcome.checks import evaluate_checks
from hse_doc_studio.core.pack_studio.outcome.documents import evaluate_documents
from hse_doc_studio.core.pack_studio.outcome.facts import facts_of
from hse_doc_studio.core.pack_studio.outcome.fields import evaluate_forms, evaluate_meta
from hse_doc_studio.core.pack_studio.outcome.inputs import (
    InputSpec,
    OutcomeInputError,
    input_specs,
    normalize_inputs,
    variants_of,
)
from hse_doc_studio.core.pack_studio.outcome.model import (
    SECTIONS,
    Alternative,
    Branch,
    Digest,
    IncludeName,
    Outcome,
    SectionName,
)
from hse_doc_studio.core.pack_studio.outcome.people import evaluate_participants
from hse_doc_studio.core.pack_studio.outcome.points import evaluate_points
from hse_doc_studio.core.pack_studio.outcome.summary import diff_sections, digest_of, fingerprint_of, section_prints
from hse_doc_studio.core.pack_studio.outcome.trace import Tracer
from hse_doc_studio.core.pack_studio.preview import PreviewExample, synthetic_project
from hse_doc_studio.use_cases.pack_studio.submission import profile_route
from hse_doc_studio.use_cases.pack_studio.synthetic_project import synthetic_core_project

__all__ = ["OutcomeInputError", "resolve"]

_EMPTY_DIGEST = Digest(documents={}, participants=(), meta_visible=(), points=(), sections=())


def synthetic_outcome_project(
    version: TemplateVersion, example: PreviewExample, combo: Mapping[str, str], today: date
) -> Project:
    """Синтетический проект результата: проект предпросмотра, у команды персоны авторов `author1..` (R11)."""
    synthetic = synthetic_project(version, example, combo, today)
    if str(synthetic.staffing) == "team":
        authors = tuple(replace(a, slug=f"author{i}") for i, a in enumerate(synthetic.authors, start=1))
        synthetic = replace(synthetic, authors=authors)
    project = synthetic_core_project(version.pack_id, version.template_id, version, synthetic)
    chosen = variants_of(version, combo)
    for doc in project.documents:
        if doc.def_id in chosen:
            doc.chosen_variant = chosen[doc.def_id]
    return project


def resolve(  # noqa: PLR0913 — версия, вводные, набор, день и режимы расчёта
    version: TemplateVersion,
    inputs: Mapping[str, str],
    example: PreviewExample,
    today: date,
    *,
    include: Collection[IncludeName] = frozenset(),
    trace: bool = True,
    revision: str = "",
) -> Outcome:
    """Результат версии для вводных. `inputs` частичные, остальное из набора данных и умолчаний версии.

    `include`: `checks` (применимость правил проверок), `branches` (что станет при каждом другом значении вводной).
    `trace=False` считает структуру без объяснений (в разы дешевле, нужен атласу). Незнакомая вводная или значение
    вне списка это `OutcomeInputError`."""
    specs = input_specs(version)
    defaults = dict(example.data.defaults) if example.data is not None else {}
    combo = normalize_inputs(specs, inputs, defaults)
    project = synthetic_outcome_project(version, example, combo, today)
    facts = facts_of(version, project, combo)
    tracer = Tracer(enabled=trace)

    documents = evaluate_documents(version, project, facts, tracer)
    meta = evaluate_meta(version, project, facts, tracer)
    forms = evaluate_forms(version, facts, tracer)
    participants = evaluate_participants(project)
    profiles = version.pack_submission.profiles if version.pack_submission is not None else ()
    routes = {profile.id: profile_route(project, version, profile) for profile in profiles}
    points = evaluate_points(version, project, facts, documents, routes, tracer)
    checks = evaluate_checks(version, documents, tracer) if "checks" in include else None

    outcome = Outcome(
        revision=revision,
        inputs=combo,
        example=example.id,
        fingerprint="",
        documents=documents,
        meta=meta,
        forms=forms,
        participants=participants,
        points=points,
        checks=checks,
        branches=None,
        digest=_EMPTY_DIGEST,
        trace=tracer.entries(),
    )
    prints = section_prints(outcome)
    outcome = replace(outcome, fingerprint=fingerprint_of(prints), digest=digest_of(outcome, prints))
    if "branches" in include:
        branches = _branches(version, specs, outcome, example, today, include)
        outcome = replace(outcome, branches=branches)
    return outcome


def _branches(  # noqa: PLR0913 — версия, вводные, исходный результат и режимы
    version: TemplateVersion,
    specs: tuple[InputSpec, ...],
    base: Outcome,
    example: PreviewExample,
    today: date,
    include: Collection[IncludeName],
) -> tuple[Branch, ...]:
    """Для каждой вводной, от которой зависит результат, что станет при каждом её значении (раздел 3.4 дизайна)."""
    inner = frozenset(name for name in include if name != "branches")
    branches: list[Branch] = []
    for spec in specs:
        alternatives: list[Alternative] = []
        affects: set[SectionName] = set()
        for value in spec.values:
            if value == base.inputs[spec.id]:
                alternatives.append(Alternative(value, spec.value_labels.get(value), base.fingerprint, ()))
                continue
            other = resolve(version, {**base.inputs, spec.id: value}, example, today, include=inner, trace=False)
            delta = diff_sections(base, other)
            affects.update(d.section for d in delta)
            alternatives.append(Alternative(value, spec.value_labels.get(value), other.fingerprint, delta))
        if affects:
            ordered = tuple(s for s in SECTIONS if s in affects)
            branches.append(
                Branch(
                    input=spec.id,
                    label=spec.label,
                    chosen=base.inputs[spec.id],
                    affects=ordered,
                    alternatives=tuple(alternatives),
                )
            )
    return tuple(branches)
