"""Раздел результата «документы»: состояние каждого документа ростера, экземпляры, итоговые имена, варианты.

Состояние берётся у движка: документ есть, если `create_project._build_documents` создал его экземпляры, и активен,
если `is_doc_active` пропускает хотя бы один из них. Рядом пишется трасса: те же условия закрытого языка (вид
работы, состав, NDA, руководства, язык) с фактическими значениями. Тест паритета держит трассу и состояние вместе.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hse_doc_studio.core.pack_studio.outcome.facts import Facts, yes_no
from hse_doc_studio.core.pack_studio.outcome.inputs import staffing_input_values
from hse_doc_studio.core.pack_studio.outcome.model import (
    DocumentOutcome,
    DocumentStateName,
    ElementRef,
    Instance,
    Term,
    VariantOption,
)
from hse_doc_studio.core.pack_studio.outcome.predicates import (
    MANUAL_MARKERS,
    NDA_DOC_ID,
    kind_allowed,
    manual_selected,
    output_arcname,
    owner_short_name,
    resolve_output_names,
    staffing_allowed,
    variant_available,
    with_owner_suffix,
)
from hse_doc_studio.core.pack_studio.outcome.trace import Tracer, builtin_rule, manifest_rule, why
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.team import author_by_slug, is_doc_active

if TYPE_CHECKING:
    from hse_doc_studio.core.catalog import DocumentDefinition, TemplateVersion
    from hse_doc_studio.core.entities import Document, Project


def doc_manifest(doc: DocumentDefinition) -> str:
    """`doc.yaml` документа от каталога версии: сюда ведёт «Править правило»."""
    return f"files/{doc.id}/doc.yaml"


def document_languages(version: TemplateVersion, doc: DocumentDefinition) -> tuple[str, ...]:
    """Языки, на которых документ написан: его `supported_langs`, иначе все языки версии."""
    return doc.supported_langs or version.langs or ("ru",)


def _state(instances: list[Document], project: Project) -> DocumentStateName:
    if not instances:
        return "absent"
    return "active" if any(is_doc_active(project, inst) for inst in instances) else "inactive"


def document_file_name(
    project: Project, doc_def: DocumentDefinition, doc: Document, lang: str, templates: ProjectTemplateService
) -> str | None:
    """Итоговое имя файла экземпляра в пакете: имя выбранного варианта на языке проекта (иначе русское, иначе имя
    файла сборки), у личного документа команды с фамилией владельца. Его читает и предпросмотр: имя собираемого
    документа совпадает с именем в результате."""
    names = resolve_output_names(doc_def, doc.chosen_variant)
    try:
        output_file = templates.resolve_document_source(doc_def, doc.chosen_variant)[1]
    except ValueError:
        output_file = ""
    if not names and not output_file:
        return None
    owner = author_by_slug(project, doc.owner)
    return with_owner_suffix(
        output_arcname(names, lang, output_file),
        owner_short_name(owner.name, owner.slug, lang) if owner is not None else None,
    )


def _instance(
    project: Project, doc_def: DocumentDefinition, doc: Document, facts: Facts, templates: ProjectTemplateService
) -> Instance:
    owner = author_by_slug(project, doc.owner)
    return Instance(
        id=doc.id,
        owner=doc.owner,
        owner_name=owner.name if owner is not None else None,
        file_name=document_file_name(project, doc_def, doc, facts.lang, templates),
    )


def evaluate_documents(  # noqa: PLR0914 — решения одного документа
    version: TemplateVersion, project: Project, facts: Facts, tracer: Tracer
) -> tuple[DocumentOutcome, ...]:
    templates = ProjectTemplateService()
    outcomes: list[DocumentOutcome] = []
    for doc_def in version.documents:
        manifest = doc_manifest(doc_def)
        subject = (ElementRef("documents", doc_def.id),)
        kind_held = kind_allowed(doc_def.supported_kinds, facts.kind)
        staffing_held = staffing_allowed(doc_def.supported_staffing, facts.staffing_mode)
        in_scope = kind_held and staffing_held
        ids = [
            tracer.decide(
                rule=manifest_rule(manifest, "/supported_kinds"),
                kind="supported_kinds",
                effect="gate",
                terms=[Term("in", "kind", tuple(doc_def.supported_kinds))],
                actual={"kind": facts.kind},
                status="held" if kind_held else "not_held",
                subjects=subject,
            ),
            tracer.decide(
                rule=manifest_rule(manifest, "/supported_staffing"),
                kind="supported_staffing",
                effect="gate",
                terms=[Term("in", "staffing", staffing_input_values(doc_def.supported_staffing))],
                actual={"staffing": facts.staffing},
                # Вид работы не подошёл: состав уже не важен, правило остаётся в цепочке серым.
                status=("held" if staffing_held else "not_held") if kind_held else "skipped",
                subjects=subject,
            ),
        ]
        ids.extend(_builtin_gates(doc_def, facts, tracer, subject, reached=in_scope))
        languages = document_languages(version, doc_def)
        lang_held = variant_available(languages, facts.lang)
        ids.append(
            tracer.decide(
                rule=manifest_rule(manifest, "/supported_langs"),
                kind="supported_langs",
                effect="display",
                terms=[Term("in", "lang", tuple(languages))],
                actual={"lang": facts.lang},
                status="held" if lang_held else "not_held",
                subjects=subject,
            )
        )
        instances = [d for d in project.documents if d.def_id == doc_def.id]
        state = _state(instances, project)
        chosen = facts.variants.get(doc_def.id) or (doc_def.variants[0].id if doc_def.variants else None)
        variants = _variants(doc_def, facts, tracer, subject, manifest) if state != "absent" else ()
        source_file: str | None = None
        if state != "absent":
            try:
                source_file = templates.resolve_document_source(doc_def, chosen)[0]
            except ValueError:
                source_file = None
        outcomes.append(
            DocumentOutcome(
                id=doc_def.id,
                name=dict(doc_def.name),
                group=doc_def.group,
                scope="personal" if doc_def.scope == "personal" else "shared",
                required=doc_def.required,
                state=state,
                lang_state="native" if lang_held else "fallback",
                languages=tuple(languages),
                variants=variants,
                instances=tuple(_instance(project, doc_def, inst, facts, templates) for inst in instances),
                source_file=source_file,
                manifest=manifest,
                why=why(*ids),
            )
        )
    return tuple(outcomes)


def _builtin_gates(
    doc_def: DocumentDefinition, facts: Facts, tracer: Tracer, subject: tuple[ElementRef, ...], *, reached: bool
) -> list[str]:
    """Зашитые в движок правила комплекта (R4 дизайна): расписка NDA и руководства по мете `manuals`."""
    if doc_def.id == NDA_DOC_ID:
        held = facts.nda
        return [
            tracer.decide(
                rule=builtin_rule("nda_gate"),
                kind="builtin_gate",
                effect="gate",
                terms=[Term("truthy", facts.nda_subject)],
                actual={facts.nda_subject: yes_no(facts.nda)},
                status=("held" if held else "not_held") if reached else "skipped",
                subjects=subject,
            )
        ]
    marker = MANUAL_MARKERS.get(doc_def.id)
    if marker is None:
        return []
    return [
        tracer.decide(
            rule=builtin_rule("manuals_gate"),
            kind="builtin_gate",
            effect="gate",
            terms=[Term("contains_any", "meta.manuals", (marker,))],
            actual={"meta.manuals": facts.manuals},
            status=("held" if manual_selected(facts.manuals, doc_def.id) else "not_held") if reached else "skipped",
            subjects=subject,
        )
    ]


def _variants(
    doc_def: DocumentDefinition, facts: Facts, tracer: Tracer, subject: tuple[ElementRef, ...], manifest: str
) -> tuple[VariantOption, ...]:
    chosen = facts.variants.get(doc_def.id) or (doc_def.variants[0].id if doc_def.variants else None)
    options: list[VariantOption] = []
    for index, variant in enumerate(doc_def.variants):
        available = variant_available(variant.supported_langs, facts.lang)
        reasons: tuple[str, ...] = ()
        if variant.supported_langs:
            reasons = why(
                tracer.decide(
                    rule=manifest_rule(manifest, f"/variants/{index}/supported_langs"),
                    kind="variant_langs",
                    effect="gate",
                    terms=[Term("in", "lang", tuple(variant.supported_langs))],
                    actual={"lang": facts.lang},
                    status="held" if available else "not_held",
                    subjects=subject,
                )
            )
        options.append(
            VariantOption(
                id=variant.id,
                label=dict(variant.label),
                langs=tuple(variant.supported_langs),
                available=available,
                chosen=variant.id == chosen,
                why=reasons,
            )
        )
    return tuple(options)
