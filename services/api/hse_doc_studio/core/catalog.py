from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from hse_doc_studio.core.enums import (
    CheckEngine,
    CheckSeverity,
    EngineType,
    FormFieldType,
    MetaFieldAuto,
    MetaFieldType,
    RequiredAt,
    TemplateVersionStatus,
)
from hse_doc_studio.core.value_objects import ChecksOverride, RequirementsFormat


@dataclass(frozen=True)
class EngineConfig:
    default: EngineType
    allowed: tuple[EngineType, ...]
    passes: int
    flags: str


@dataclass(frozen=True)
class SignatureDefaultPlacement:
    page: int
    x_mm: float
    y_mm: float
    width_mm: float


@dataclass(frozen=True)
class SignatureSlotDef:
    id: str
    label: dict[str, str]
    applies_to: tuple[str, ...]
    default_placement: SignatureDefaultPlacement
    # Team mode: слот размножается по авторам — рантайм-слоты "{id}--{slug}"
    # (свой PNG у каждого автора). applies_to при этом трактуется как def id:
    # слот автора применим к ЕГО личным докам и ко всем shared (общие доки
    # подписывают все авторы). В solo не влияет.
    per_author: bool = False

    # Поля `required_for` здесь СОЗНАТЕЛЬНО НЕТ. Обязательность подписи — это
    # свойство пары «документ + контрольная точка», а не документа: одно и то же
    # ТЗ на КТ2 сдаётся без подписи руководителя, а на ГИА — обязательно с ней.
    # Статическое поле этот смысл выразить не могло и разошлось с профилями
    # сдачи на 11 пар в ВКР и 5 в курсовой: панель размещения молчала о подписи,
    # которую финальный комплект затем требовал. Единственный источник знания —
    # `pack_submission.profiles[].items[].signatures`; выводит его
    # `SignatureSlotService.required_by_profiles`.


@dataclass(frozen=True)
class DocumentVariant:
    id: str
    label: dict[str, str]
    source_file: str
    output_file: str
    output_name: dict[str, str]
    engine: EngineType | None
    # Языки проекта, в которых вариант доступен для выбора (IEEE/ISO-редакции
    # ЕСПД-доков — только en). Пустой кортеж → вариант доступен во всех языках.
    supported_langs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentDefinition:
    id: str
    name: dict[str, str]
    code: dict[str, str]
    source_file: str | None
    output_file: str | None
    output_name: dict[str, str]
    gost_ref: str | None
    required: bool
    checks: ChecksOverride
    # Languages whose source is actually authored/maintained for this doc.
    # Empty tuple → treat as "all template languages" (legacy templates that
    # haven't declared this explicitly yet).
    supported_langs: tuple[str, ...] = ()
    variants: tuple[DocumentVariant, ...] = ()
    # "personal" — в team-проекте по экземпляру на ведомого автора (в его
    # папке); "shared" — один экземпляр (team: в shared/, solo: в корне).
    # В solo personal==shared: один экземпляр в корне. Defaults to "shared".
    scope: str = "shared"
    # В каких режимах состава документ существует. Общее ТЗ объявляет [team] —
    # в solo-проекте оно не инстанцируется вовсе.
    supported_staffing: tuple[str, ...] = ("solo", "team")
    # В каких форматах ВКР документ существует: "project" (проектный формат —
    # ЕСПД-комплект ТЗ/ПМИ/ТП/РП/РО) и/или "research" (академический,
    # исследовательский формат — Аннотация вместо ТЗ, без софт-документации).
    # По умолчанию оба (общие для форматов документы: сама ВКР, презентация).
    # Документ, чей формат не совпадает с project.kind, не инстанцируется и его
    # файлы-скелет не копируются в проект.
    supported_kinds: tuple[str, ...] = ("research", "project")
    # Визуальный блок в навигации (espd/pdp/pres/…): фронтенд рисует дивайдер
    # между соседними документами разных групп. None — вне блоков (дивайдер по
    # обе стороны от смены значения). Чисто презентационное поле.
    group: str | None = None


@dataclass(frozen=True)
class MetaFieldDef:
    type: MetaFieldType
    label: dict[str, str]
    placeholder: str | None
    required_at: RequiredAt
    help: dict[str, str] | None
    # Static literal pre-fill applied at creation when the user leaves the field
    # blank (e.g. degree_type -> "Бакалавриат").
    default: Any | None
    # Computed pre-fill derived from "now" at creation (e.g. defense year). Takes
    # precedence over `default` when both are set. See core.meta_defaults.
    auto: MetaFieldAuto | None = None
    options: tuple[str, ...] = ()
    # Id of a `meta_groups` entry — the settings UI renders fields of one
    # group under a shared subheading. None → the trailing ungrouped bucket.
    group: str | None = None
    # "project" — одно значение на проект (по умолчанию); "author" — у каждого
    # автора своё значение (живёт в Author.meta), а одноимённый project.meta
    # ключ несёт «системное» значение для shared-доков (fallback в рендере).
    scope: str = "project"
    # Виды работы, в которых поле показывается (research/project). Пусто/оба =
    # во всех видах. Напр. `manuals` (РП/РО) — только project: в исследовательском
    # формате руководств нет.
    supported_kinds: tuple[str, ...] = ("research", "project")


@dataclass(frozen=True)
class MetaGroupDef:
    """A named group of meta fields; declaration order = display order."""

    id: str
    label: dict[str, str]
    # Страница настроек проекта, на которой показывается группа: "meta" —
    # «Метаданные» (по умолчанию), "documents" — «Документы». Состав комплекта
    # (какие руководства входят) — решение о документах, а не очередное поле
    # титульного листа, поэтому пак вправе увести группу к форматам шаблонов.
    section: str = "meta"


@dataclass(frozen=True)
class CheckRule:
    id: str
    title: dict[str, str]
    description: dict[str, str]
    category: str | None
    applies_to: list[str] | Literal["*"]
    default_severity: CheckSeverity
    engine: CheckEngine
    params: dict[str, Any]


@dataclass(frozen=True)
class CheckSource:
    """One `checks/*.yaml` file describing the document whose rules it encodes.

    Rule ids are `"<source>/<short-name>"`, where `<source>` is the file basename —
    that prefix is how a rule is attributed back to its source. The pack owns these
    labels: the app must not hardcode names of standards or study programmes, since
    another pack may target a different programme or university entirely.
    """

    id: str
    # Short heading for grouping rules in the UI ("ГОСТ 7.32-2017").
    label: dict[str, str]
    # Full citation of the referenced document, section included ("ГОСТ 7.32-2017 §6").
    ref: dict[str, str]
    # Who issued it, and where to read it.
    source: dict[str, str]
    url: str | None = None


@dataclass(frozen=True)
class FormOption:
    """A choice in a `select` / `multiselect` field."""

    id: str
    label: dict[str, str]
    default: bool = False


@dataclass(frozen=True)
class FormColumn:
    """A column of a repeatable `table` field. Cells are free text."""

    id: str
    label: dict[str, str]


@dataclass(frozen=True)
class VisibleIf:
    """Show the owning field only when answers[field] == equals.

    The single conditional primitive the engine supports — enough to model the
    used/not-used branch of the AI declaration. Intentionally not a full
    expression language.
    """

    field: str
    equals: Any


@dataclass(frozen=True)
class FormFieldDef:
    """One question in a pack-declared form. `id` keys the answer value."""

    id: str
    type: FormFieldType
    label: dict[str, str]
    help: dict[str, str] | None = None
    placeholder: dict[str, str] | None = None
    required: bool = False
    options: tuple[FormOption, ...] = ()  # select / multiselect
    columns: tuple[FormColumn, ...] = ()  # table
    min: float | None = None  # number
    max: float | None = None  # number
    step: float | None = None  # number
    min_length: int | None = None  # text / textarea
    default: Any | None = None
    # A presentational hint for the renderer (e.g. "slider" for a number,
    # "radio"/"chips" for select/multiselect). Never affects the value shape.
    widget: str | None = None
    visible_if: VisibleIf | None = None
    # For `markdown` (display-only) blocks: the static rich text to render.
    content: dict[str, str] | None = None


@dataclass(frozen=True)
class FormSection:
    """An ordered group of fields, rendered as one block in the UI."""

    id: str
    title: dict[str, str]
    fields: tuple[FormFieldDef, ...]


@dataclass(frozen=True)
class FormOutputConfig:
    """How a filled form is rendered into a deliverable artifact.

    `template` is a path relative to the version directory (Jinja over the
    project + the form's answers); `format` is currently always "markdown".
    """

    template: str
    output_name: str
    format: str = "markdown"


@dataclass(frozen=True)
class FormDefinition:
    """A pack-declared questionnaire. The whole point of the engine: the pack
    describes the form, the backend stores raw keyed answers, the frontend
    renders fields generically — nothing per-field is hardcoded.
    """

    id: str
    title: dict[str, str]
    sections: tuple[FormSection, ...]
    schema_version: int = 1
    # When True, an incomplete/invalid form surfaces a warning at pack
    # submission time (it does NOT hard-block the build).
    required_for_pack: bool = False
    output: FormOutputConfig | None = None
    # Optional presentational hint for the nav/page icon (e.g. "bot",
    # "clipboard"). The frontend maps it to a concrete icon; unknown/None falls
    # back to a generic form icon. Keeps the engine fully generic — there is no
    # special "AI declaration" type, just a form that can pick its icon.
    icon: str | None = None
    # Team mode: форма заполняется каждым ведомым автором отдельно —
    # рантайм-инстансы "{id}--{slug}" со своим стейтом ответов. В solo — одна.
    per_author: bool = False
    # Виды проекта, где форма показывается и рендерится (как у документов и
    # meta-полей). Напр. «Ссылка на код» — только research: программный вид
    # сдаёт Текст программы, а не ссылку.
    supported_kinds: tuple[str, ...] = ("research", "project")


@dataclass(frozen=True)
class SubmissionDocItem:
    doc_id: str
    signatures: tuple[str, ...]
    # ЛМС-правило «под NDA документ не сдаётся» (защита КП: расписка NDA
    # заменяет Текст программы). True → пункт пропускается при meta.nda.
    skip_if_nda: bool = False
    # Виды проекта, где пункт применяется (как supported_kinds документов).
    # Нужен, когда сам ДОКУМЕНТ существует в обоих видах, а в комплект КТ
    # входит только в одном (напр. thesis на КТ2 ВКР — только проектный:
    # research сдаёт вместо глав 1–2 «Отчёт ВКР»).
    supported_kinds: tuple[str, ...] = ("research", "project")


@dataclass(frozen=True)
class ExtraSubmissionItem:
    source: str
    output_name: str
    format: str | None
    # Виды проекта, где extra попадает в пакет (как supported_kinds документов).
    # Напр. «Ссылка на код.txt»: на КТ2 — только research, на защите — оба.
    supported_kinds: tuple[str, ...] = ("research", "project")


@dataclass(frozen=True)
class SubmissionProfile:
    id: str
    name: dict[str, str]
    description: dict[str, str]
    items: tuple[SubmissionDocItem, ...]
    extra_items: tuple[ExtraSubmissionItem, ...]


@dataclass(frozen=True)
class PackSubmissionConfig:
    profiles: tuple[SubmissionProfile, ...]


@dataclass(frozen=True)
class ChecksVersionConfig:
    disabled_categories: tuple[str, ...]
    disabled: tuple[str, ...]
    severity_override: dict[str, CheckSeverity]


@dataclass(frozen=True)
class NdaConfig:
    """A pack-provided NDA file group toggled by `project.meta.nda`.

    When the project is marked NDA, the files under `source_dir` (relative to
    the version's `files/`) are instantiated into the project (so the student
    fills/signs them) and included in every submission package under
    `submission_dir`. When NDA is off, none of this happens — toggling the flag
    is literally toggling this folder in/out of the project and the package.
    """

    source_dir: str
    submission_dir: str = "NDA"


@dataclass(frozen=True)
class DynamicInclude:
    """A pack file regenerated from the project on EVERY compile (and at
    creation), not baked once like the rest of the sources.

    `template` is a path (relative to the version's `files/` dir) to a Jinja
    source rendered against the project context (LaTeX-safe delimiters);
    `output` is the path (relative to the project folder) where the rendered
    result is written. This is how changeable data (author/supervisor names,
    group, NDA flag, …) reaches the compiled PDF without re-rendering — and
    without touching the user's own `.tex` files: those `\\input` the generated
    output and reference macros defined in it.
    """

    template: str
    output: str


@dataclass(frozen=True)
class SignaturesConfig:
    slots: tuple[SignatureSlotDef, ...]


@dataclass(frozen=True)
class TemplateVersion:
    pack_id: str
    template_id: str
    version: str
    status: TemplateVersionStatus
    released_at: date
    summary: dict[str, str]
    engine_config: EngineConfig
    required_tex_packages: tuple[str, ...]
    documents: tuple[DocumentDefinition, ...]
    meta_fields: dict[str, MetaFieldDef]
    signatures_config: SignaturesConfig
    pack_submission: PackSubmissionConfig
    checks_config: ChecksVersionConfig
    rules: tuple[CheckRule, ...]
    # Metadata of the checks/*.yaml files the rules came from, keyed by `id`
    # (= the rule-id prefix). Empty for packs whose files carry no header.
    check_sources: tuple[CheckSource, ...] = ()
    # Pack-level default for how requirements are detected (see version.yaml
    # `requirements:`). Projects may override via Project.requirements_format.
    requirements_format: RequirementsFormat = field(default_factory=RequirementsFormat)
    # Declared display groups for meta_fields (order = display order).
    meta_groups: tuple[MetaGroupDef, ...] = ()
    # Pack-declared questionnaires (the generic forms engine). The AI
    # declaration is just one of these forms — there is no special type.
    forms: tuple[FormDefinition, ...] = ()
    # Files regenerated from the project on every compile (see DynamicInclude).
    # The canonical use is `common/meta.tex` — the macro bundle carrying all
    # changeable project data (names, group, NDA, …) into the LaTeX build.
    dynamic_includes: tuple[DynamicInclude, ...] = ()
    # Optional NDA file group, toggled by project.meta.nda (see NdaConfig).
    nda: NdaConfig | None = None
    # Какие режимы состава шаблон умеет порождать. Пак без "team" нельзя
    # выбрать для проекта с >1 автором (визард блокирует).
    supported_staffing: tuple[str, ...] = ("solo",)
    # v2 (bundle-раскладка): объявленные языковые коды суффиксов имён файлов
    # (`<stem>.<код>.<ext>`); первый в списке = дефолт и фолбэк. Пустой кортеж
    # — v1-раскладка (lang/-оверлеи), суффиксы не распознаются.
    langs: tuple[str, ...] = ()

    def get_form(self, form_id: str) -> FormDefinition | None:
        for form in self.forms:
            if form.id == form_id:
                return form
        return None


@dataclass(frozen=True)
class TemplateInfo:
    pack_id: str
    id: str
    name: dict[str, str]
    short_name: dict[str, str]
    description: dict[str, str]
    icon: str
    accent_hue: int
    default_version: str


@dataclass(frozen=True)
class PackInfo:
    id: str
    name: dict[str, str]
    description: dict[str, str]
    maintainer: dict[str, str]
    license: str
    templates: tuple[TemplateInfo, ...]
