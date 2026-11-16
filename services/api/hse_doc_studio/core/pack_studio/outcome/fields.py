"""Разделы результата «метаданные» и «анкеты»: видимость, обязательность, значения и условия `visible_if`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hse_doc_studio.core.pack_studio.outcome.facts import Facts, yes_no
from hse_doc_studio.core.pack_studio.outcome.inputs import answer_input_id
from hse_doc_studio.core.pack_studio.outcome.model import (
    ElementRef,
    FormFieldOutcome,
    FormOutcome,
    MetaOutcome,
    Term,
)
from hse_doc_studio.core.pack_studio.outcome.predicates import (
    field_visible_for_kind,
    kind_allowed,
    kinds_restrict,
    visible_if_held,
)
from hse_doc_studio.core.pack_studio.outcome.trace import Tracer, manifest_rule, why

if TYPE_CHECKING:
    from hse_doc_studio.core.catalog import TemplateVersion
    from hse_doc_studio.core.entities import Project

VERSION_MANIFEST = "version.yaml"


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return yes_no(value)
    return str(value)


def evaluate_meta(version: TemplateVersion, project: Project, facts: Facts, tracer: Tracer) -> tuple[MetaOutcome, ...]:
    """Поля проекта версии: видимость по виду работы, обязательность, значение синтетического проекта, опции."""
    fields: list[MetaOutcome] = []
    for field_id, definition in version.meta_fields.items():
        visible = field_visible_for_kind(definition.supported_kinds, facts.kind)
        reasons: tuple[str, ...] = ()
        if kinds_restrict(definition.supported_kinds):
            reasons = why(
                tracer.decide(
                    rule=manifest_rule(VERSION_MANIFEST, f"/meta_fields/{field_id}/supported_kinds"),
                    kind="field_kinds",
                    effect="display",
                    terms=[Term("in", "kind", tuple(definition.supported_kinds))],
                    actual={"kind": facts.kind},
                    status="held" if visible else "not_held",
                    subjects=[ElementRef("meta", field_id)],
                )
            )
        is_person = definition.type.value == "person"
        fields.append(
            MetaOutcome(
                id=field_id,
                type=definition.type.value,
                label=dict(definition.label),
                scope=definition.scope,
                group=definition.group,
                visible=visible,
                required_at=definition.required_at.value,
                value=None if is_person else _text(project.meta.get(field_id)),
                options=tuple(str(option) for option in definition.options),
                why=reasons,
            )
        )
    return tuple(fields)


def _expected(value: Any) -> str:
    return yes_no(value) if isinstance(value, bool) else str(value)


def evaluate_forms(version: TemplateVersion, facts: Facts, tracer: Tracer) -> tuple[FormOutcome, ...]:
    """Анкеты версии: применимость к виду работы, поля с видимостью по ответам и обязательностью."""
    forms: list[FormOutcome] = []
    for form_index, form in enumerate(version.forms):
        applies = kind_allowed(form.supported_kinds, facts.kind)
        form_why: tuple[str, ...] = ()
        if kinds_restrict(form.supported_kinds):
            form_why = why(
                tracer.decide(
                    rule=manifest_rule(VERSION_MANIFEST, f"/forms/{form_index}/supported_kinds"),
                    kind="form_kinds",
                    effect="gate",
                    terms=[Term("in", "kind", tuple(form.supported_kinds))],
                    actual={"kind": facts.kind},
                    status="held" if applies else "not_held",
                    subjects=[ElementRef("forms", form.id)],
                )
            )
        answers = facts.answers.get(form.id, {})
        fields: list[FormFieldOutcome] = []
        for section_index, section in enumerate(form.sections):
            for field_index, field in enumerate(section.fields):
                condition = field.visible_if
                held = visible_if_held(condition, answers)
                reasons: tuple[str, ...] = ()
                if condition is not None:
                    subject = answer_input_id(form.id, condition.field)
                    given = answers.get(condition.field)
                    pointer = f"/forms/{form_index}/sections/{section_index}/fields/{field_index}/visible_if"
                    reasons = why(
                        tracer.decide(
                            rule=manifest_rule(VERSION_MANIFEST, pointer),
                            kind="visible_if",
                            effect="display",
                            terms=[Term("equals", subject, (_expected(condition.equals),))],
                            actual={subject: _expected(given) if given is not None else ""},
                            status=("held" if held else "not_held") if applies else "skipped",
                            subjects=[ElementRef("forms", f"{form.id}/{field.id}")],
                        )
                    )
                fields.append(
                    FormFieldOutcome(
                        id=field.id,
                        type=field.type.value,
                        label=dict(field.label),
                        visible=applies and held,
                        # Обязательность в этой комбинации: скрытое поле и поясняющий текст не требуют ответа
                        # (как у проверки анкеты `FormValidationService.validate`).
                        required=field.required and applies and held and field.type.value != "markdown",
                        why=reasons,
                    )
                )
        forms.append(
            FormOutcome(
                id=form.id,
                title=dict(form.title),
                per_author=form.per_author,
                applies=applies,
                required_for_pack=form.required_for_pack,
                fields=tuple(fields),
                why=form_why,
            )
        )
    return tuple(forms)
