"""Линтер результата версии: статические правила, правила по атласу и универсум покрытия (раздел 6 дизайна, срез O8).

Чистая функция над разобранной версией (файлов не читает, времени не берёт): версию, тексты манифестов и набор данных
вызывающий уже прочитал. Атлас строится как у эндпоинта `outcome/atlas` (`build_atlas`: измерения по анализу влияния),
затем результат каждой строки таблицы считается с трассой, и `AtlasObserver` собирает по ним находки и универсум
правил. Больше предела строк (`atlas_too_large`) правила по атласу не идут: ответ несёт статические находки и
информационную находку `atlas-skipped`, а покрытие считается приближённо.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.atlas import ATLAS_MAX_ROWS, Atlas, AtlasTooLarge
from hse_doc_studio.core.pack_studio.outcome.coverage import RuleUniverse
from hse_doc_studio.core.pack_studio.outcome.inputs import InputSpec, input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.lint import (
    RULES,
    VERSION_MANIFEST,
    LintFinding,
    LintSources,
    doc_manifest,
    drop_nested,
    finding,
    limit_per_rule,
    with_lines,
)
from hse_doc_studio.core.pack_studio.outcome.lint_atlas import AtlasObservation, AtlasObserver
from hse_doc_studio.core.pack_studio.outcome.lint_static import static_findings
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef
from hse_doc_studio.core.pack_studio.preview import PreviewExample
from hse_doc_studio.use_cases.pack_studio.outcome.atlas import build_atlas, example_defaults
from hse_doc_studio.use_cases.pack_studio.outcome.impact import ImpactAnalysis
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve

# Вводные групп, чьё «ни на что не влияет» стоит показать автору: поля проекта, ответы анкет и варианты документов.
_NO_EFFECT_GROUPS = frozenset({"meta", "answers", "variants"})
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_RULE_ORDER = {rule: index for index, (rule, _, _) in enumerate(RULES)}


@dataclass(frozen=True, slots=True)
class AtlasScan:
    """Обход строк атласа: сам атлас (измерения, исходы) и то, что по ним видно правилам и покрытию."""

    atlas: Atlas
    observation: AtlasObservation

    @property
    def universe(self) -> RuleUniverse:
        return self.observation.universe


@dataclass(frozen=True, slots=True)
class OutcomeLint:
    """Находки линтера результата и универсум покрытия (None: атлас слишком большой)."""

    findings: tuple[LintFinding, ...]
    universe: RuleUniverse | None
    rows: int
    atlas_skipped: bool = False

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


def scan_atlas(  # noqa: PLR0913 — версия, набор, день, предел, готовый анализ и проверка срока
    version: TemplateVersion,
    example: PreviewExample,
    today: date,
    *,
    limit: int = ATLAS_MAX_ROWS,
    analysis: ImpactAnalysis | None = None,
    check: Callable[[], None] | None = None,
    texts: Mapping[str, str] | None = None,
) -> AtlasScan:
    """Атлас версии и результат с трассой в каждой его строке. `AtlasTooLarge`, если строк больше `limit`. `texts`
    тексты манифестов (где лежат документы), без них места документов берутся из `files/<id>/doc.yaml`."""
    atlas = build_atlas(version, example, today, limit=limit, analysis=analysis, check=check)
    base = normalize_inputs(input_specs(version), {}, example_defaults(example))
    names = [dimension.input for dimension in atlas.dimensions]
    observer = AtlasObserver(LintSources(version, texts or {}), names)
    for values in itertools.product(*(dimension.values for dimension in atlas.dimensions)):
        if check is not None:
            check()
        outcome = resolve(version, {**base, **dict(zip(names, values, strict=True))}, example, today)
        observer.observe(values, outcome)
    return AtlasScan(atlas, observer.finish())


def _answer_pointer(version: TemplateVersion, form_id: str, field_id: str) -> tuple[str, str, ElementRef] | None:
    for f_index, form in enumerate(version.forms):
        for s_index, section in enumerate(form.sections):
            for i_index, item in enumerate(section.fields):
                if (form.id, item.id) == (form_id, field_id):
                    pointer = f"/forms/{f_index}/sections/{s_index}/fields/{i_index}"
                    return VERSION_MANIFEST, pointer, ElementRef("forms", f"{form_id}/{field_id}")
    return None


def _no_effect_pointer(version: TemplateVersion, spec: InputSpec) -> tuple[str, str, ElementRef | None]:
    """Файл, указатель и элемент вводной, которая ни на что не влияет."""
    if spec.id.startswith("meta."):
        key = spec.id.removeprefix("meta.")
        return VERSION_MANIFEST, f"/meta_fields/{key}", ElementRef("meta", key)
    if spec.id.startswith("variant."):
        doc_id = spec.id.removeprefix("variant.")
        return doc_manifest(doc_id), "/variants", ElementRef("documents", doc_id)
    form_id, _, field_id = spec.id.removeprefix("answer.").partition(".")
    return _answer_pointer(version, form_id, field_id) or (VERSION_MANIFEST, "/", None)


def dimension_findings(version: TemplateVersion, atlas: Atlas) -> tuple[LintFinding, ...]:
    """Поле select или bool, которое не влияет ни на что, кроме печати: информационная находка (нормально для
    текстовых подстановок)."""
    no_effect = {item.input for item in atlas.ignored if item.reason == "no_effect"}
    found: list[LintFinding] = []
    for spec in input_specs(version):
        if spec.id not in no_effect or spec.group not in _NO_EFFECT_GROUPS:
            continue
        file, pointer, element = _no_effect_pointer(version, spec)
        found.append(
            finding(
                "dimension-no-effect",
                "info",
                f"Вводная «{spec.id}» не влияет ни на документы, ни на участников, ни на точки и маршрут: "
                "результат одинаков при любом её значении.",
                "Нормально, если поле только печатается в документах. Иначе проверьте условия, которые должны "
                "его читать.",
                file,
                pointer,
                *([element] if element is not None else []),
            )
        )
    return tuple(found)


def _skipped(rows: int, limit: int) -> LintFinding:
    return finding(
        "atlas-skipped",
        "info",
        f"Таблица исходов версии ({rows} строк) больше предела {limit}: правила по атласу и точное покрытие "
        "пропущены, остались статические правила.",
        "Сузьте вводные (меньше полей select и bool) или закрепите часть вводных через pin на экране.",
        None,
        None,
    )


def order_findings(findings: tuple[LintFinding, ...]) -> tuple[LintFinding, ...]:
    """Ошибки раньше предупреждений, внутри по порядку правил раздела 6.1, дальше как найдены."""
    return tuple(
        sorted(findings, key=lambda f: (_SEVERITY_ORDER[f.severity], _RULE_ORDER.get(f.rule_id, len(_RULE_ORDER))))
    )


def lint_outcome(  # noqa: PLR0913 — версия, тексты, набор данных, день, предел и проверка срока
    version: TemplateVersion,
    texts: Mapping[str, str],
    example: PreviewExample,
    today: date,
    *,
    limit: int = ATLAS_MAX_ROWS,
    scan: AtlasScan | None = None,
    check: Callable[[], None] | None = None,
) -> OutcomeLint:
    """Находки линтера результата версии. `scan` готовый обход атласа (служба кэширует его для покрытия)."""
    sources = LintSources(version, texts)
    static = static_findings(sources)
    try:
        scan = scan or scan_atlas(version, example, today, limit=limit, check=check, texts=texts)
    except AtlasTooLarge as exc:
        return OutcomeLint(order_findings((*static, _skipped(exc.rows, exc.limit))), None, 0, atlas_skipped=True)
    # Находка по атласу точнее статической с тем же правилом и местом: идёт первой, повтор склеивается.
    merged = (*scan.observation.findings, *dimension_findings(version, scan.atlas), *static)
    return OutcomeLint(
        order_findings(with_lines(limit_per_rule(drop_nested(merged)), texts)),
        scan.universe,
        len(scan.universe.rows),
    )
