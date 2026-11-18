"""Линтер результата: модель находки и общие приёмы (раздел 6 дизайна результата, срез O8).

Правила бывают трёх видов. Статические (`lint_static.py`) читают версию и сырые тексты манифестов: ни расчёта, ни
перебора, мгновенно, входят в общий список «Проблемы» рядом с находками `pack_lint`. Правила по атласу
(`lint_atlas.py`) смотрят на результат в каждой строке атласа. Правила по файлам (Jinja,
`infra/pack_studio/outcome_lint_files.py`) читают шаблоны и запускаются по кнопке.

У каждой находки код правила, серьёзность, понятное сообщение, подсказка («как исправить»), место (`file` от каталога
версии, `pointer` JSON Pointer внутри файла и `line`), затронутые элементы результата и до трёх комбинаций вводных,
на которых видно (`witnesses`): кнопка «Показать» ставит экран в нужную комбинацию.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import yaml
from yaml.nodes import MappingNode, Node, SequenceNode

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef

type Severity = Literal["error", "warning", "info"]
type Witness = dict[str, str]

VERSION_MANIFEST = "version.yaml"
# Находок одного правила в ответе не больше этого: остальные считаются, но не перечисляются (одна опечатка в общем
# условии не должна давать сотню одинаковых строк).
MAX_PER_RULE = 50
MAX_WITNESSES = 3
MAX_ELEMENTS = 16

# Все правила линтера результата в порядке раздела 6.1 дизайна: код, серьёзность по умолчанию, источник.
RULES: tuple[tuple[str, Severity, str], ...] = (
    ("slot-never-routed", "warning", "atlas"),
    ("route-step-without-person", "warning", "atlas"),
    ("route-gap", "warning", "atlas"),
    ("visible-if-unknown-field", "error", "static"),
    ("visible-if-value-not-in-options", "error", "static"),
    ("required-hidden", "error", "static+atlas"),
    ("field-never-visible", "warning", "atlas"),
    ("variant-lang-outside-langs", "error", "static"),
    ("skip-if-nda-without-nda", "warning", "static"),
    ("when-unknown-person", "error", "static"),
    ("when-never-held", "warning", "atlas"),
    ("when-always-held", "info", "atlas"),
    ("slot-when-overlap", "warning", "atlas"),
    ("document-never-active", "warning", "atlas"),
    ("item-never-active", "warning", "atlas"),
    ("point-empty", "info", "atlas"),
    ("translation-missing", "warning", "static"),
    ("builtin-gate-mismatch", "warning", "static"),
    ("dimension-no-effect", "info", "atlas"),
    ("jinja-fail-open", "error", "files"),
    ("jinja-unknown-meta-key", "warning", "files"),
    ("atlas-skipped", "info", "atlas"),
)
RULE_IDS: frozenset[str] = frozenset(rule for rule, _, _ in RULES)


@dataclass(frozen=True, slots=True)
class LintFinding:
    """Находка линтера результата (`OutcomeFinding` контракта плюс `hint`)."""

    rule_id: str
    severity: Severity
    message: str
    hint: str
    file: str | None
    pointer: str | None
    line: int | None = None
    elements: tuple[ElementRef, ...] = ()
    witnesses: tuple[Witness, ...] = ()

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        """Одна находка на правило и место: повтор одного дефекта разными путями склеивается."""
        return self.rule_id, self.file, self.pointer


def drop_nested(findings: Iterable[LintFinding]) -> tuple[LintFinding, ...]:
    """Находка о вложенном месте уходит, если то же правило уже назвало охватывающее (анкета не применима, а у
    каждого её поля то же самое)."""
    items = tuple(findings)
    outer: set[tuple[str, str | None, str | None]] = {(f.rule_id, f.file, f.pointer) for f in items if f.pointer}
    return tuple(f for f in items if not _has_outer(f, outer))


def _has_outer(item: LintFinding, outer: set[tuple[str, str | None, str | None]]) -> bool:
    parts = [part for part in (item.pointer or "").split("/") if part]
    return any((item.rule_id, item.file, "/" + "/".join(parts[:n])) in outer for n in range(1, len(parts)))


def limit_per_rule(findings: Iterable[LintFinding], limit: int = MAX_PER_RULE) -> tuple[LintFinding, ...]:
    """Склейка повторов и предел числа находок одного правила (порядок сохранён)."""
    seen: set[tuple[str, str | None, str | None]] = set()
    counts: dict[str, int] = {}
    kept: list[LintFinding] = []
    for finding in findings:
        if finding.key in seen:
            continue
        seen.add(finding.key)
        if counts.get(finding.rule_id, 0) >= limit:
            continue
        counts[finding.rule_id] = counts.get(finding.rule_id, 0) + 1
        kept.append(finding)
    return tuple(kept)


# ── Вход ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LintSources:
    """Версия и тексты её манифестов (`version.yaml`, `files/<документ>/doc.yaml`) для строк и сырых записей."""

    version: TemplateVersion
    texts: Mapping[str, str] = field(default_factory=dict)

    def raw_version(self) -> Mapping[str, Any]:
        """Разобранный `version.yaml`; пусто, если не разобран (линтер пака уже назвал это ошибкой)."""
        try:
            data = yaml.safe_load(self.texts.get(VERSION_MANIFEST, ""))
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}


def doc_manifest(doc_id: str) -> str:
    return f"files/{doc_id}/doc.yaml"


def doc_site(sources: LintSources, doc_id: str) -> tuple[str, str]:
    """Файл и указатель документа в манифесте: `files/<id>/doc.yaml` (корень) или запись в `documents` версии (шаблон
    старого вида, где документ описан прямо в `version.yaml`)."""
    manifest = doc_manifest(doc_id)
    if manifest in sources.texts or not sources.texts:
        return manifest, ""
    index = next((i for i, doc in enumerate(sources.version.documents) if doc.id == doc_id), 0)
    return VERSION_MANIFEST, f"/documents/{index}"


class _Lines:
    """Строка (с единицы) узла по файлу и JSON Pointer; тексты разбираются один раз."""

    def __init__(self, texts: Mapping[str, str]) -> None:
        self._texts = texts
        self._trees: dict[str, Node | None] = {}

    def of(self, file: str | None, pointer: str | None) -> int | None:
        if file is None or pointer is None or file not in self._texts:
            return None
        if file not in self._trees:
            try:
                self._trees[file] = yaml.compose(self._texts[file], Loader=yaml.SafeLoader)
            except yaml.YAMLError:
                self._trees[file] = None
        return _line_of(self._trees[file], [part for part in pointer.split("/") if part])


def _line_of(tree: Node | None, parts: list[str]) -> int | None:
    if tree is None:
        return None
    node: Node = tree
    line = node.start_mark.line + 1
    for part in parts:
        if isinstance(node, MappingNode):
            entry = next(((k, v) for k, v in node.value if str(k.value) == part), None)
            if entry is None:
                break
            key, node = entry
            line = key.start_mark.line + 1
        elif isinstance(node, SequenceNode) and part.isdigit() and int(part) < len(node.value):
            node = node.value[int(part)]
            line = node.start_mark.line + 1
        else:
            break
    return line


def with_lines(findings: Iterable[LintFinding], texts: Mapping[str, str]) -> tuple[LintFinding, ...]:
    """Строки находок по их файлу и указателю (где строка ещё не задана)."""
    lines = _Lines(texts)
    return tuple(f if f.line is not None else replace(f, line=lines.of(f.file, f.pointer)) for f in findings)


def finding(  # noqa: PLR0913 — код, серьёзность, текст, подсказка и место
    rule_id: str,
    severity: Severity,
    message: str,
    hint: str,
    file: str | None,
    pointer: str | None,
    *elements: ElementRef,
) -> LintFinding:
    return LintFinding(rule_id, severity, message, hint, file, pointer, None, elements[:MAX_ELEMENTS])
