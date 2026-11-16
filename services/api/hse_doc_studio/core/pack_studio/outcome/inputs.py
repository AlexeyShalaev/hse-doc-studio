"""Вводные версии шаблона: словарь для панели и разбор вводных запроса (раздел 2.1 дизайна результата).

Вводная это одна ось, на которую автор влияет у проекта. Все значения строки (`yes` и `no` у логических), как в
комбинации предпросмотра: состояние кладётся в адрес страницы. Словарь строится из схемы версии, ни одной вводной в
клиенте не прописано:

- `project`: `lang`, `kind`, `staffing` (`solo`, `team2`, `team3`);
- `people`: `supervisor` (`university`, `company`, `none`), `co_supervisor`, `academic_supervisor` (`yes`, `no`);
- `meta`: `nda` (у версии есть блок `nda`) и `meta.<поле>` у каждого поля select и bool;
- `answers`: `answer.<анкета>.<поле>` у полей select и bool, которые читает `visible_if`;
- `variants`: `variant.<документ>` у документов, у которых есть из чего выбрать при любом языке.

Переключатели предпросмотра (`switches_for`) остаются источником первых трёх групп: вычислитель и предпросмотр
считают комбинацию одним и тем же кодом (`resolve_combination`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from hse_doc_studio.core.enums import FormFieldType, MetaFieldType
from hse_doc_studio.core.pack_studio.preview import (
    META_SWITCH_PREFIX,
    NO,
    STAFFING_SOLO,
    STAFFING_TEAMS,
    SWITCH_ACADEMIC,
    SWITCH_CO_SUPERVISOR,
    SWITCH_KIND,
    SWITCH_LANG,
    SWITCH_NDA,
    SWITCH_STAFFING,
    SWITCH_SUPERVISOR,
    YES,
    PreviewInputError,
    PreviewSwitch,
    resolve_combination,
    switches_for,
)

if TYPE_CHECKING:
    from hse_doc_studio.core.catalog import FormDefinition, FormFieldDef, TemplateVersion

ANSWER_PREFIX = "answer."
VARIANT_PREFIX = "variant."

type InputGroup = Literal["project", "people", "meta", "answers", "variants"]

_PROJECT_INPUTS = frozenset({SWITCH_LANG, SWITCH_KIND, SWITCH_STAFFING})
_PEOPLE_INPUTS = frozenset({SWITCH_SUPERVISOR, SWITCH_CO_SUPERVISOR, SWITCH_ACADEMIC})


class OutcomeInputError(ValueError):
    """Вводная не подходит к версии: на границе это `inputs_invalid` с полями `field`, `value` и `reason`."""

    def __init__(self, field: str, value: str, reason: str) -> None:
        super().__init__(f"{field}={value!r}: {reason}")
        self.field = field
        self.value = value
        self.reason = reason


@dataclass(frozen=True, slots=True)
class InputSpec:
    """Вводная панели: идентификатор, группа, тип, подписи и допустимые значения."""

    id: str
    group: InputGroup
    type: Literal["select", "bool"]
    label: dict[str, str] | None
    values: tuple[str, ...]
    default: str
    # Подписи значений (`{ru, en}`), у части значений нет.
    value_labels: Mapping[str, dict[str, str]]

    def as_switch(self) -> PreviewSwitch:
        return PreviewSwitch(self.id, self.values, self.default, self.label)


def nda_input_id(version: TemplateVersion) -> str:
    """Вводная NDA: `nda`, если версия объявляет блок `nda`, иначе поле проекта `meta.nda`."""
    return SWITCH_NDA if version.nda is not None else f"{META_SWITCH_PREFIX}{SWITCH_NDA}"


def staffing_input_values(modes: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Значения вводной `staffing` для режимов состава документа: `solo` это `solo`, `team` это `team2` и `team3`."""
    values: list[str] = []
    if STAFFING_SOLO in modes:
        values.append(STAFFING_SOLO)
    if "team" in modes:
        values.extend(STAFFING_TEAMS)
    return tuple(values)


def _group_of(switch_id: str) -> InputGroup:
    if switch_id in _PROJECT_INPUTS:
        return "project"
    if switch_id in _PEOPLE_INPUTS:
        return "people"
    return "meta"


def _switch_type(version: TemplateVersion, switch_id: str) -> Literal["select", "bool"]:
    """Логическая вводная: переключатель людей и NDA, поле проекта типа bool; остальное выбор из списка."""
    if switch_id in (SWITCH_CO_SUPERVISOR, SWITCH_ACADEMIC, SWITCH_NDA):
        return "bool"
    field = (
        version.meta_fields.get(switch_id.removeprefix(META_SWITCH_PREFIX))
        if switch_id.startswith(META_SWITCH_PREFIX)
        else None
    )
    return "bool" if field is not None and field.type is MetaFieldType.bool_ else "select"


def answer_input_id(form_id: str, field_id: str) -> str:
    return f"{ANSWER_PREFIX}{form_id}.{field_id}"


def variant_input_id(doc_id: str) -> str:
    return f"{VARIANT_PREFIX}{doc_id}"


def _answer_choice(field: FormFieldDef) -> tuple[tuple[str, ...], str, dict[str, dict[str, str]]] | None:
    """Значения, умолчание и подписи поля анкеты, от которого зависит видимость; None: перечислить нельзя."""
    if field.type is FormFieldType.bool_:
        return (NO, YES), (YES if field.default is True else NO), {}
    if field.type is FormFieldType.select and field.options:
        values = tuple(option.id for option in field.options)
        default = str(field.default) if field.default is not None and str(field.default) in values else values[0]
        return values, default, {option.id: dict(option.label) for option in field.options if option.label}
    return None


def _form_fields(form: FormDefinition) -> dict[str, FormFieldDef]:
    return {field.id: field for section in form.sections for field in section.fields}


def answer_inputs(version: TemplateVersion) -> tuple[InputSpec, ...]:
    """Вводные ответов анкет: поля select и bool, которые читает `visible_if` другого поля той же анкеты."""
    specs: list[InputSpec] = []
    seen: set[str] = set()
    for form in version.forms:
        fields = _form_fields(form)
        for field in fields.values():
            condition = field.visible_if
            if condition is None:
                continue
            source = fields.get(condition.field)
            input_id = answer_input_id(form.id, condition.field)
            choice = _answer_choice(source) if source is not None else None
            if source is None or choice is None or input_id in seen:
                continue
            seen.add(input_id)
            values, default, labels = choice
            specs.append(
                InputSpec(
                    id=input_id,
                    group="answers",
                    type="bool" if choice[0] == (NO, YES) and source.type is FormFieldType.bool_ else "select",
                    label=dict(source.label),
                    values=values,
                    default=default,
                    value_labels=labels,
                )
            )
    return tuple(specs)


def variant_inputs(version: TemplateVersion) -> tuple[InputSpec, ...]:
    """Вводные вариантов: документ, у которого не меньше двух вариантов доступны при любом языке проекта.

    Вариант только для одного языка (редакция IEEE у ЕСПД-документа) вводной не делает: выбор зависит от `lang`, а
    не от автора, доступность такого варианта видна в результате (`variants[].available`)."""
    specs: list[InputSpec] = []
    for doc in version.documents:
        open_variants = [variant for variant in doc.variants if not variant.supported_langs]
        if len(open_variants) < 2:  # noqa: PLR2004 — выбирать не из чего
            continue
        values = tuple(variant.id for variant in open_variants)
        first = doc.variants[0].id
        specs.append(
            InputSpec(
                id=variant_input_id(doc.id),
                group="variants",
                type="select",
                label=dict(doc.name),
                values=values,
                default=first if first in values else values[0],
                value_labels={variant.id: dict(variant.label) for variant in open_variants},
            )
        )
    return tuple(specs)


def input_specs(version: TemplateVersion) -> tuple[InputSpec, ...]:
    """Все вводные версии в порядке панели: проект, люди, поля, ответы анкет, варианты документов."""
    specs: list[InputSpec] = []
    for switch in switches_for(version, max_meta=None):
        values = switch.values
        specs.append(
            InputSpec(
                id=switch.id,
                group=_group_of(switch.id),
                type=_switch_type(version, switch.id),
                label=dict(switch.label) if switch.label else None,
                values=values,
                default=switch.default,
                value_labels={},
            )
        )
    specs.extend(answer_inputs(version))
    specs.extend(variant_inputs(version))
    return tuple(specs)


def normalize_inputs(
    specs: tuple[InputSpec, ...], raw: Mapping[str, str], example_defaults: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Полные вводные: значение из запроса, иначе из набора данных (если подходит), иначе по умолчанию.

    Незнакомая вводная или значение вне списка это `OutcomeInputError`. Порядок ключей как у словаря вводных."""
    try:
        return resolve_combination([spec.as_switch() for spec in specs], raw, example_defaults)
    except PreviewInputError as exc:
        field = exc.field.removeprefix("combination.")
        raise OutcomeInputError(field, exc.value, exc.reason) from None


def answers_of(version: TemplateVersion, inputs: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """Ответы анкет, как их читает `visible_if`: у bool-поля булево, у select id варианта (`form -> field -> ответ`)."""
    answers: dict[str, dict[str, Any]] = {}
    for form in version.forms:
        fields = _form_fields(form)
        for field_id, field in fields.items():
            raw = inputs.get(answer_input_id(form.id, field_id))
            if raw is None:
                continue
            answers.setdefault(form.id, {})[field_id] = (raw == YES) if field.type is FormFieldType.bool_ else raw
    return answers


def variants_of(version: TemplateVersion, inputs: Mapping[str, str]) -> dict[str, str]:
    """Выбранный вариант документа: вводная `variant.<документ>`, иначе первый вариант."""
    chosen: dict[str, str] = {}
    for doc in version.documents:
        if not doc.variants:
            continue
        chosen[doc.id] = inputs.get(variant_input_id(doc.id)) or doc.variants[0].id
    return chosen
