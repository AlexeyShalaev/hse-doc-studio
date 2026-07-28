from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from hse_doc_studio.core.catalog import (
    CheckRule,
    ChecksVersionConfig,
    DocumentDefinition,
    DocumentVariant,
    FormDefinition,
    FormFieldDef,
    SignatureSlotDef,
    SubmissionDocItem,
    SubmissionProfile,
    TemplateVersion,
)
from hse_doc_studio.core.entities import ChatMessage, ChatSummaryBlock, Document, Project
from hse_doc_studio.core.enums import (
    ChatContentKind,
    ChatMessageRole,
    CheckSeverity,
    EngineType,
    FormFieldType,
    Lang,
    ProjectStaffing,
    RequirementFormatKind,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.team import (
    OWNER_SEPARATOR,
    doc_base_dir,
    is_doc_active,
    prefix_path,
    split_instance_id,
)
from hse_doc_studio.core.value_objects import (
    Author,
    ChecksOverride,
    FormValidationError,
    RequirementsFormat,
    SignaturesState,
)

_TEXTUAL = (FormFieldType.text, FormFieldType.textarea)


class FormValidationService:
    """Validates raw form answers against a pack-declared FormDefinition.

    Pure domain logic, no I/O. Validation is advisory: it produces a list of
    unmet requirements and a derived `is_complete` flag the API surfaces so the
    UI can warn the student. It never raises and never blocks anything — gating
    policy lives at the submission layer.

    A field is only validated when it is *visible* (its `visible_if` condition,
    if any, is satisfied by the current answers), so the hidden branch of a
    used/not-used toggle is never spuriously "required".
    """

    def validate(self, form: FormDefinition, answers: dict[str, Any]) -> list[FormValidationError]:
        errors: list[FormValidationError] = []
        for section in form.sections:
            for fld in section.fields:
                if fld.type == FormFieldType.markdown:
                    continue
                if not self.is_visible(fld, answers):
                    continue
                errors.extend(self._validate_field(fld, answers.get(fld.id)))
        return errors

    def is_complete(self, form: FormDefinition, answers: dict[str, Any]) -> bool:
        return not self.validate(form, answers)

    def is_visible(self, fld: FormFieldDef, answers: dict[str, Any]) -> bool:
        cond = fld.visible_if
        if cond is None:
            return True
        return answers.get(cond.field) == cond.equals

    def _validate_field(self, fld: FormFieldDef, value: Any) -> list[FormValidationError]:
        # Messages follow the request's interface language (independent of the
        # document language); the label itself is also taken in that language.
        lang = current_interface_language()
        en = lang is Lang.en
        label = fld.label.get(lang.value) or fld.label.get("ru") or fld.label.get("en") or fld.id
        errors: list[FormValidationError] = []

        if self._is_empty(fld, value):
            if fld.required:
                msg = f"Field «{label}» is required" if en else f"Поле «{label}» обязательно для заполнения"
                errors.append(FormValidationError(fld.id, msg))
            return errors  # nothing more to check on an empty value

        if (
            fld.type in _TEXTUAL
            and fld.min_length is not None
            and isinstance(value, str)
            and len(value.strip()) < fld.min_length
        ):
            msg = (
                f"«{label}»: at least {fld.min_length} characters"
                if en
                else f"«{label}»: минимум {fld.min_length} символов"
            )
            errors.append(FormValidationError(fld.id, msg))

        if fld.type == FormFieldType.number and isinstance(value, int | float) and not isinstance(value, bool):
            if fld.min is not None and value < fld.min:
                msg = f"«{label}»: must be at least {fld.min}" if en else f"«{label}»: значение не меньше {fld.min}"
                errors.append(FormValidationError(fld.id, msg))
            if fld.max is not None and value > fld.max:
                msg = f"«{label}»: must be at most {fld.max}" if en else f"«{label}»: значение не больше {fld.max}"
                errors.append(FormValidationError(fld.id, msg))

        return errors

    def _is_empty(self, fld: FormFieldDef, value: Any) -> bool:
        if value is None:
            return True
        if fld.type == FormFieldType.bool_:
            # A required boolean is a consent toggle: unchecked counts as unmet.
            return value is not True
        if fld.type == FormFieldType.number:
            return False  # any number (including 0) is a present value
        if fld.type in (FormFieldType.multiselect, FormFieldType.table):
            return not value  # empty list / no rows
        if isinstance(value, str):
            return value.strip() == ""
        return not value


_CHARS_PER_TOKEN = 4


class ChatContextService:
    """Pure policy for when to compact a chat transcript and what to keep.

    No I/O and no LLM call — it decides (a) whether the replayed context is over
    budget and (b) the cutoff seq below which older messages are folded into a
    rolling summary, always keeping a recent verbatim tail and never splitting a
    tool_call from its tool_result. The summarization itself (an LLM call) and
    persistence live elsewhere.
    """

    def estimate_tokens(self, system: str, messages: list[ChatMessage], summaries: list[ChatSummaryBlock]) -> int:
        total = len(system) // _CHARS_PER_TOKEN
        total += sum(len(s.text) // _CHARS_PER_TOKEN for s in summaries)
        total += sum(self._message_tokens(m) for m in messages)
        return total

    def needs_compaction(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        summaries: list[ChatSummaryBlock],
        token_budget: int,
        trigger_ratio: float,
    ) -> bool:
        if token_budget <= 0:
            return False
        return self.estimate_tokens(system, messages, summaries) >= trigger_ratio * token_budget

    def plan_cutoff(
        self,
        messages: list[ChatMessage],
        *,
        keep_recent_tokens: int,
        keep_recent_messages_min: int,
    ) -> int | None:
        """Return the seq below/at which messages should be summarized, or None.

        Walks newest→oldest accumulating the verbatim tail until both the token
        and message-count floors are met, then nudges the boundary earlier so the
        kept region never starts with an orphan tool_result.
        """
        if len(messages) <= keep_recent_messages_min:
            return None
        kept_tokens = 0
        split = len(messages)
        for i in range(len(messages) - 1, -1, -1):
            kept_tokens += self._message_tokens(messages[i])
            split = i
            kept_count = len(messages) - i
            if kept_tokens >= keep_recent_tokens and kept_count >= keep_recent_messages_min:
                break
        while 0 < split < len(messages) and messages[split].role == ChatMessageRole.tool:
            split -= 1
        if split <= 0:
            return None
        return messages[split - 1].seq

    def _message_tokens(self, message: ChatMessage) -> int:
        chars = 0
        for block in message.blocks:
            if block.kind == ChatContentKind.text and block.text:
                chars += len(block.text)
            elif block.kind == ChatContentKind.tool_call:
                chars += len(block.tool_name or "") + len(str(block.args))
            elif block.kind == ChatContentKind.tool_result and block.result:
                chars += len(block.result)
        return chars // _CHARS_PER_TOKEN


class CheckResolutionService:
    def resolve(
        self,
        rules: list[CheckRule],
        doc_id: str,
        version_cfg: ChecksVersionConfig,
        doc_definition_checks: ChecksOverride,
        project_override: ChecksOverride,
        doc_override: ChecksOverride,
        user_override: ChecksOverride,
    ) -> list[tuple[CheckRule, CheckSeverity]]:
        candidates = self._filter_by_scope(rules, doc_id)
        state = self._apply_version_config(candidates, version_cfg)
        # Each override layer narrows or expands `state` against the same pool
        # of `candidates`. Order is pack → user:
        #   rule defaults → version → doc-definition → project → doc → user
        # The first three come from the pack YAML (intent of the pack author);
        # the last three are user-set runtime overrides.
        state = self._apply_override(candidates, state, doc_definition_checks)
        state = self._apply_override(candidates, state, project_override)
        state = self._apply_override(candidates, state, doc_override)
        return self._apply_override(candidates, state, user_override)

    def resolve_for_project(
        self,
        rules: list[CheckRule],
        doc_ids: set[str],
        version_cfg: ChecksVersionConfig,
        project_override: ChecksOverride,
    ) -> list[tuple[CheckRule, CheckSeverity]]:
        """Resolve rules at project scope.

        Used for the project-level rules management view: returns rules whose
        `applies_to` intersects with any document in the project, after the
        version → project override chain. Doc/user layers are intentionally
        skipped — those are document-scoped.
        """
        candidates = self._filter_by_scope_any(rules, doc_ids)
        state = self._apply_version_config(candidates, version_cfg)
        return self._apply_override(candidates, state, project_override)

    def _filter_by_scope(
        self,
        rules: list[CheckRule],
        doc_id: str,
    ) -> list[tuple[CheckRule, CheckSeverity]]:
        result: list[tuple[CheckRule, CheckSeverity]] = []
        for rule in rules:
            applies = rule.applies_to == "*" or (isinstance(rule.applies_to, list) and doc_id in rule.applies_to)
            if applies:
                result.append((rule, rule.default_severity))
        return result

    def _filter_by_scope_any(
        self,
        rules: list[CheckRule],
        doc_ids: set[str],
    ) -> list[tuple[CheckRule, CheckSeverity]]:
        result: list[tuple[CheckRule, CheckSeverity]] = []
        for rule in rules:
            if rule.applies_to == "*":
                result.append((rule, rule.default_severity))
                continue
            if isinstance(rule.applies_to, list) and any(d in rule.applies_to for d in doc_ids):
                result.append((rule, rule.default_severity))
        return result

    def _apply_version_config(
        self,
        candidates: list[tuple[CheckRule, CheckSeverity]],
        version_cfg: ChecksVersionConfig,
    ) -> list[tuple[CheckRule, CheckSeverity]]:
        result: list[tuple[CheckRule, CheckSeverity]] = []
        for rule, severity in candidates:
            if rule.category is not None and rule.category in version_cfg.disabled_categories:
                continue
            if rule.id in version_cfg.disabled:
                continue
            effective = version_cfg.severity_override.get(rule.id, severity)
            result.append((rule, effective))
        return result

    def _apply_override(
        self,
        candidates: list[tuple[CheckRule, CheckSeverity]],
        current: list[tuple[CheckRule, CheckSeverity]],
        override: ChecksOverride,
    ) -> list[tuple[CheckRule, CheckSeverity]]:
        """Apply one override layer (project/doc/user — same logic) on top of current state."""
        # Rules dropped by previous layers — eligible for re-enable.
        disabled_now = {rule.id for rule, _ in candidates} - {rule.id for rule, _ in current}

        next_state: list[tuple[CheckRule, CheckSeverity]] = []
        for rule, severity in current:
            if rule.category is not None and rule.category in override.disabled_categories:
                continue
            if rule.id in override.disabled:
                continue
            effective = override.severity_override.get(rule.id, severity)
            next_state.append((rule, effective))

        next_ids = {rule.id for rule, _ in next_state}
        for rule, severity in candidates:
            if rule.id in disabled_now and rule.id in override.enabled and rule.id not in next_ids:
                effective = override.severity_override.get(rule.id, severity)
                next_state.append((rule, effective))

        return next_state


class ProjectTemplateService:
    def get_default_version(
        self,
        pack_id: str,
        template_id: str,
        template_repo: ITemplateRepository,
    ) -> TemplateVersion:
        packs = template_repo.list_packs()
        pack = next((p for p in packs if p.id == pack_id), None)
        if pack is None:
            raise NotFoundError(localized_error(f"Пак не найден: {pack_id!r}", f"Pack not found: {pack_id!r}"))
        template_info = next((t for t in pack.templates if t.id == template_id), None)
        if template_info is None:
            raise NotFoundError(
                localized_error(
                    f"Шаблон не найден: {template_id!r} в паке {pack_id!r}",
                    f"Template not found: {template_id!r} in pack {pack_id!r}",
                )
            )
        version = template_repo.get_version(pack_id, template_id, template_info.default_version)
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия по умолчанию {template_info.default_version!r} не найдена для {pack_id!r}/{template_id!r}",
                    f"Default version {template_info.default_version!r} not found for {pack_id!r}/{template_id!r}",
                )
            )
        return version

    @staticmethod
    def _choose_variant(doc_def: DocumentDefinition, chosen_variant: str | None) -> DocumentVariant:
        """Выбранный вариант документа; fallback на первый (нет выбора/id)."""
        if chosen_variant is None:
            return doc_def.variants[0]
        return next(
            (v for v in doc_def.variants if v.id == chosen_variant),
            doc_def.variants[0],
        )

    def resolve_document_source(
        self,
        doc_def: DocumentDefinition,
        chosen_variant: str | None,
    ) -> tuple[str, str]:
        if doc_def.variants:
            variant = self._choose_variant(doc_def, chosen_variant)
            return (variant.source_file, variant.output_file)

        if doc_def.source_file is None or doc_def.output_file is None:
            raise ValueError(
                localized_error(
                    f"У документа {doc_def.id!r} нет source_file/output_file и вариантов",
                    f"Document {doc_def.id!r} has no source_file/output_file and no variants",
                )
            )
        return (doc_def.source_file, doc_def.output_file)

    def resolve_document_engine(
        self,
        doc_def: DocumentDefinition | None,
        chosen_variant: str | None,
        lock_engine: EngineType,
    ) -> EngineType | None:
        """Движок компиляции инстанса документа.

        У вариантного дока — движок ВЫБРАННОГО варианта (fallback на первый,
        как в resolve_document_source); None — copy-only вариант (pptx/reveal).
        Без вариантов (и когда определение не найдено) — движок из lock
        проекта.
        """
        if doc_def is not None and doc_def.variants:
            return self._choose_variant(doc_def, chosen_variant).engine
        return lock_engine

    def find_definition(self, version: TemplateVersion, doc: Document) -> DocumentDefinition | None:
        """Определение пака для инстанса документа — join строго по def_id.

        (`doc.id` в team-проекте несёт суффикс владельца и с id пака не
        совпадает; все места вида `d.id == doc_id` должны идти через это.)
        """
        return next((d for d in version.documents if d.id == doc.def_id), None)

    def resolve_instance_source(
        self,
        project: Project,
        doc: Document,
        version: TemplateVersion,
    ) -> tuple[str, str]:
        """(source_file, output_file) инстанса относительно КОРНЯ проекта.

        Solo — как в паке («tz/tz.tex»); team — с префиксом базы владельца
        («shalaev/tz/tz.tex», shared-доки — «shared/…»).
        """
        doc_def = self.find_definition(version, doc)
        if doc_def is None:
            raise NotFoundError(
                localized_error(
                    f"Определение документа не найдено для {doc.def_id!r}",
                    f"Document definition not found for {doc.def_id!r}",
                )
            )
        # Bundle-раскладка: дерево пака == дереву проекта, пути манифеста уже
        # в проектном пространстве — достаточно префикса базы владельца.
        source, output = self.resolve_document_source(doc_def, doc.chosen_variant)
        base = doc_base_dir(project, doc)
        return (prefix_path(base, source), prefix_path(base, output))

    def custom_upload_dir(self, project: Project, doc: Document, version: TemplateVersion) -> str:
        """Storage path (relative to project root) for `doc`'s custom upload.

        Reuses the exact same source→instance resolution chain as
        `resolve_instance_source` to find the document's own top-level
        directory, then reserves a `_custom/` subdirectory under it — e.g.
        `tz/_custom/ТЗ.docx` (solo), `shalaev/vkr/_custom/thesis.pdf` (team
        personal), `shared/tz/_custom/tz.pdf` (team shared). This is a raw
        directory path; the caller appends the sanitized filename.
        """
        doc_def = self.find_definition(version, doc)
        if doc_def is None:
            raise NotFoundError(
                localized_error(
                    f"Определение документа не найдено для {doc.def_id!r}",
                    f"Document definition not found for {doc.def_id!r}",
                )
            )
        source, _output = self.resolve_document_source(doc_def, doc.chosen_variant)
        top_dir = source.replace("\\", "/").split("/", 1)[0]
        base = doc_base_dir(project, doc)
        return prefix_path(base, f"{top_dir}/_custom")

    def instance_dir_map(self, project: Project, version: TemplateVersion) -> dict[str, str]:
        """Map каталога инстанса (POSIX от корня, «tz» / «shalaev/tz») → doc.id.

        Instance-aware замена doc_dir_map: атрибуция файла к документу идёт по
        самому длинному совпавшему префиксу пути (см. вызывающих в
        requirements). Первый инстанс выигрывает при коллизии каталогов.
        """
        def_dirs: dict[str, str] = {}
        for doc_def in version.documents:
            source = doc_def.source_file
            if source is None and doc_def.variants:
                source = doc_def.variants[0].source_file
            if not source:
                continue
            top = source.replace("\\", "/").split("/", 1)[0].strip().lower()
            if top:
                def_dirs.setdefault(doc_def.id, top)
        mapping: dict[str, str] = {}
        for doc in project.documents:
            top = def_dirs.get(doc.def_id)
            if not top:
                continue
            base = doc_base_dir(project, doc)
            mapping.setdefault(prefix_path(base, top).lower(), doc.id)
        return mapping

    def doc_dir_map(self, version: TemplateVersion) -> dict[str, str]:
        """Map each document's top-level source directory → doc_id.

        Derived from the template's document definitions (`source_file`, or the
        first variant's `source_file` for variant-only docs like a presentation),
        so callers can attribute a file to the document that owns it without a
        hardcoded table — pack-specific or renamed folders are handled
        automatically. First declaration wins on a directory collision.
        """
        mapping: dict[str, str] = {}
        for doc in version.documents:
            source = doc.source_file
            if source is None and doc.variants:
                source = doc.variants[0].source_file
            if not source:
                continue
            top = source.replace("\\", "/").split("/", 1)[0].strip().lower()
            if top:
                mapping.setdefault(top, doc.id)
        return mapping


def resolve_form_instance(
    project: Project,
    version: TemplateVersion,
    form_instance_id: str,
) -> tuple[FormDefinition, Author | None]:
    """Инстанс формы → (определение пака, автор-владелец|None).

    Solo и формы без per_author живут под базовым id. В team форма с
    `per_author: true` существует ТОЛЬКО как инстансы "{form}--{slug}" (свой
    стейт ответов у каждого автора); обращение по базовому id — ошибка,
    как и инстанс для формы без per_author.
    """
    base_id, owner_slug = split_instance_id(form_instance_id)
    form = version.get_form(base_id)
    # Форма другого вида проекта (supported_kinds) для этого проекта не
    # существует — как документ, отфильтрованный по kind.
    if form is not None and str(project.kind) not in form.supported_kinds:
        form = None
    if form is None:
        raise NotFoundError(
            localized_error(
                f"Форма {form_instance_id!r} не найдена в этом проекте",
                f"Form {form_instance_id!r} not found for this project",
            )
        )
    team = project.staffing == ProjectStaffing.team
    if owner_slug is None:
        if team and form.per_author:
            raise ValueError(
                localized_error(
                    f"Форма {base_id!r} — персональная, обращайтесь к инстансу «{base_id}--<slug>»",
                    f"Form {base_id!r} is per-author — address the instance '{base_id}--<slug>'",
                )
            )
        return form, None
    if not (team and form.per_author):
        raise ValueError(
            localized_error(
                f"У формы {base_id!r} нет персональных инстансов",
                f"Form {base_id!r} has no per-author instances",
            )
        )
    author = next((a for a in project.authors if a.slug == owner_slug), None)
    if author is None:
        raise NotFoundError(
            localized_error(
                f"Автор {owner_slug!r} не найден в проекте",
                f"Author {owner_slug!r} not found in project",
            )
        )
    return form, author


@dataclass(frozen=True)
class RuntimeSlot:
    """Рантайм-слот подписи проекта.

    Solo — слоты как в паке. Team — слоты с `per_author: true` размножаются по
    авторам: id "{slot}--{slug}", PNG у каждого свой; лейбл получает ФИО.
    Применимость к документу считается от def_id (пак перечисляет id
    определений) и владельца: per-author слот применим к личным докам своего
    автора и ко всем общим (общие доки подписывают все авторы).
    """

    id: str
    slot_def: SignatureSlotDef
    owner: str | None
    label: dict[str, str]


def expand_slot_ids_for_doc(
    slot_ids: tuple[str, ...],
    slot_defs: dict[str, SignatureSlotDef],
    project: Project,
    doc: Document,
    *,
    team: bool,
) -> list[str]:
    """Базовые id слотов из профиля → рантайм-id для конкретного документа.

    В команде per-author слот размножен на «{slot}--{slug}»: у личного документа
    подписывает его владелец, у общего — все авторы. Функция модульная, а не
    метод: её одинаково нужны и формирование комплекта, и вывод обязательности
    подписи, а разошедшиеся копии этой логики означали бы, что панель показывает
    одно, а упаковка требует другое.
    """
    if not team:
        return list(slot_ids)
    expanded: list[str] = []
    for slot_id in slot_ids:
        slot_def = slot_defs.get(slot_id)
        if slot_def is None or not slot_def.per_author:
            expanded.append(slot_id)
        elif doc.owner is not None:
            expanded.append(f"{slot_id}{OWNER_SEPARATOR}{doc.owner}")
        else:
            expanded.extend(f"{slot_id}{OWNER_SEPARATOR}{a.slug}" for a in project.authors if a.slug)
    return expanded


class SignatureSlotService:
    def runtime_slots(self, project: Project, version: TemplateVersion) -> list[RuntimeSlot]:
        team = project.staffing == ProjectStaffing.team
        slots: list[RuntimeSlot] = []
        for slot_def in version.signatures_config.slots:
            if team and slot_def.per_author:
                for author in project.authors:
                    if not author.slug:
                        continue
                    label = {lang: f"{text} — {author.name}" for lang, text in slot_def.label.items()} or {
                        "ru": author.name
                    }
                    slots.append(
                        RuntimeSlot(
                            id=f"{slot_def.id}{OWNER_SEPARATOR}{author.slug}",
                            slot_def=slot_def,
                            owner=author.slug,
                            label=label,
                        )
                    )
            else:
                slots.append(RuntimeSlot(id=slot_def.id, slot_def=slot_def, owner=None, label=dict(slot_def.label)))
        return slots

    def find_runtime_slot(self, project: Project, version: TemplateVersion, slot_id: str) -> RuntimeSlot | None:
        return next((s for s in self.runtime_slots(project, version) if s.id == slot_id), None)

    def slot_applies_to_doc(self, slot: RuntimeSlot, doc: Document) -> bool:
        return self._matches(slot, doc, slot.slot_def.applies_to)

    def required_by_profiles(
        self,
        project: Project,
        version: TemplateVersion,
    ) -> dict[str, dict[str, tuple[str, ...]]]:
        """Где подпись обязательна и НА КАКОЙ контрольной точке.

        Возвращает `runtime slot id -> doc instance id -> id профилей`.

        Обязательность выводится из профилей сдачи, а не объявляется отдельным
        полем слота: она свойство пары «документ + точка», а не документа. Пока
        обязательность дублировалась полем `required_for`, два источника
        разошлись — панель размещения не помечала подписи, которых финальный
        комплект затем требовал, и упаковка отказывала уже после того, как
        студент считал документы подписанными.

        Фильтры пунктов профиля повторяют `SubmissionService.package_items`:
        документ под NDA и пункт чужого вида проекта в комплект не входят, а
        значит и подпись на них не обязательна.
        """
        profiles = version.pack_submission.profiles if version.pack_submission is not None else ()
        if not profiles:
            return {}

        slots = {s.id: s for s in self.runtime_slots(project, version)}
        slot_defs = {s.id: s for s in version.signatures_config.slots}
        team = project.staffing == ProjectStaffing.team
        result: dict[str, dict[str, list[str]]] = {}

        for profile in profiles:
            for item in profile.items:
                if self._item_out_of_scope(item, project):
                    continue
                for slot_id, doc_id in self._required_pairs(item, project, slots, slot_defs, team=team):
                    seen = result.setdefault(slot_id, {}).setdefault(doc_id, [])
                    if profile.id not in seen:
                        seen.append(profile.id)

        return {slot_id: {doc_id: tuple(ids) for doc_id, ids in docs.items()} for slot_id, docs in result.items()}

    def _required_pairs(
        self,
        item: SubmissionDocItem,
        project: Project,
        slots: dict[str, RuntimeSlot],
        slot_defs: dict[str, SignatureSlotDef],
        *,
        team: bool,
    ) -> Iterator[tuple[str, str]]:
        """Пары «слот, экземпляр документа», подпись на которых требует пункт."""
        for doc in project.documents:
            if doc.def_id != item.doc_id or not is_doc_active(project, doc):
                continue
            for runtime_id in expand_slot_ids_for_doc(item.signatures, slot_defs, project, doc, team=team):
                # Пункт профиля может назвать слот, неприменимый к этому
                # экземпляру: личный слот соавтора на чужом документе.
                slot = slots.get(runtime_id)
                if slot is not None and self.slot_applies_to_doc(slot, doc):
                    yield runtime_id, doc.id

    @staticmethod
    def _item_out_of_scope(item: SubmissionDocItem, project: Project) -> bool:
        """Пункт профиля, который в комплект этого проекта не попадёт вовсе.

        Повторяет фильтры `SubmissionService.package_items`: если документа в
        комплекте не будет, то и подпись на нём не обязательна.
        """
        if item.skip_if_nda and bool(project.meta.get("nda")):
            return True
        return str(project.kind) not in item.supported_kinds

    @staticmethod
    def _matches(slot: RuntimeSlot, doc: Document, def_ids: tuple[str, ...]) -> bool:
        if doc.def_id not in def_ids:
            return False
        if slot.owner is None:
            return True
        return doc.owner is None or doc.owner == slot.owner


class SubmissionProfileService:
    def get_profile(
        self,
        version: TemplateVersion,
        profile_id: str,
    ) -> SubmissionProfile | None:
        return next(
            (p for p in version.pack_submission.profiles if p.id == profile_id),
            None,
        )

    def build_item_list(
        self,
        profile: SubmissionProfile,
        project: Project,
        version: TemplateVersion,
        sig_state: SignaturesState,
        author_slug: str | None = None,
    ) -> list[SubmissionDocItem]:
        """Разворачивает пункты профиля (id ОПРЕДЕЛЕНИЙ) в инстансы документов.

        Solo — как раньше, один инстанс на пункт. Team — пакет формируется
        per-author: личные доки берутся у `author_slug`, общие — из shared-базы;
        слоты с `per_author` разворачиваются в рантайм-id ("author--slug" у
        личного дока; у общего — слоты ВСЕХ авторов: общее ТЗ подписывает
        команда целиком).
        """
        team = project.staffing == ProjectStaffing.team
        if team and not author_slug:
            raise ValueError(
                localized_error(
                    "Командный проект: укажите автора, чей пакет сдачи формируется",
                    "Team project: specify the author whose submission package is being built",
                )
            )
        slot_defs = {s.id: s for s in version.signatures_config.slots}
        result: list[SubmissionDocItem] = []

        for item in profile.items:
            # ЛМС-правило «под NDA документ не сдаётся» (напр. Текст программы
            # на защите: его заменяет расписка NDA).
            if item.skip_if_nda and bool(project.meta.get("nda")):
                continue
            # Пункт другого вида проекта (supported_kinds) — пропускается,
            # даже если сам документ существует в обоих видах.
            if str(project.kind) not in item.supported_kinds:
                continue
            instances = self._resolve_profile_instances(item.doc_id, project, version, author_slug=author_slug)
            for doc in instances:
                runtime_ids = self._expand_item_slots(item.signatures, slot_defs, project, doc, team=team)
                validated = self._validated_signatures(doc, runtime_ids, sig_state)
                result.append(SubmissionDocItem(doc_id=doc.id, signatures=tuple(validated)))

        return result

    def resolve_profile_doc_instances(
        self,
        profile: SubmissionProfile,
        project: Project,
        version: TemplateVersion,
        author_slug: str | None = None,
    ) -> list[Document]:
        """Same document-instance resolution as `build_item_list`, but WITHOUT
        signature-completeness validation — for read-only inspection (e.g. the
        custom-file packaging preflight) that must not fail just because a
        required signature isn't filled in yet. That validation only matters
        at actual package-build time.
        """
        team = project.staffing == ProjectStaffing.team
        if team and not author_slug:
            raise ValueError(
                localized_error(
                    "Командный проект: укажите автора, чей пакет сдачи формируется",
                    "Team project: specify the author whose submission package is being built",
                )
            )
        result: list[Document] = []
        for item in profile.items:
            if item.skip_if_nda and bool(project.meta.get("nda")):
                continue
            if str(project.kind) not in item.supported_kinds:
                continue
            result.extend(self._resolve_profile_instances(item.doc_id, project, version, author_slug=author_slug))
        return result

    @staticmethod
    def _resolve_profile_instances(
        def_id: str,
        project: Project,
        version: TemplateVersion,
        *,
        author_slug: str | None,
    ) -> list[Document]:
        team = project.staffing == ProjectStaffing.team
        instances = [
            d
            for d in project.documents
            if d.def_id == def_id
            and (not team or d.owner is None or d.owner == author_slug)
            # Невыбранное руководство (РП/РО) в пакет сдачи не попадает.
            and is_doc_active(project, d)
        ]
        if not instances:
            known_defs = {d.id for d in version.documents}
            if def_id in known_defs:
                # Определение есть в паке, но не инстанцировано в этом
                # проекте (tz_shared в solo; выключенная shared-база;
                # неведомый автор) — пункт профиля просто пропускается.
                return []
            raise NotFoundError(
                localized_error(
                    f"Документ {def_id!r} требуется профилем, но не найден в проекте",
                    f"Document {def_id!r} required by profile but not found in project",
                )
            )
        return instances

    @staticmethod
    def _validated_signatures(doc: Document, runtime_ids: list[str], sig_state: SignaturesState) -> list[str]:
        validated: list[str] = []
        doc_placements = sig_state.placements.get(doc.id, {})
        for slot_id in runtime_ids:
            placement = doc_placements.get(slot_id)
            slot = sig_state.slots.get(slot_id)
            if placement is None or not placement.enabled or slot is None or slot.png_path is None:
                raise ValueError(
                    localized_error(
                        f"Для документа {doc.id!r} требуется слот подписи {slot_id!r}, "
                        f"но он не включён или у него нет PNG в состоянии подписей проекта",
                        f"Signature slot {slot_id!r} required for document {doc.id!r} "
                        f"but not enabled or missing PNG in project signatures state",
                    )
                )
            validated.append(slot_id)
        return validated

    # Развёртка per-author слотов вынесена в модульную expand_slot_ids_for_doc:
    # ею пользуется и вывод обязательности подписи (SignatureSlotService).
    _expand_item_slots = staticmethod(expand_slot_ids_for_doc)


# ---------------------------------------------------------------------------
# Requirements traceability: configurable detection of definitions / references
# ---------------------------------------------------------------------------

# Default \req{ID}{text} / \reqref{ID} convention (RequirementFormatKind.macro).
# The id may start with a Cyrillic letter too — the ЕСПД convention is «ТЗ-Ф-01».
_MACRO_DEF_PATTERN = r"\\req(?:\[[^\]]*\])?\{(?P<id>[A-Za-zА-Яа-яЁё][\w.-]*)\}\{(?P<title>(?:[^{}]|\{[^{}]*\})*)\}"
_MACRO_REF_PATTERN = r"\\reqref\{(?P<ids>[^}]+)\}"

# When kind=id and no definition documents are configured, treat the TZ as the
# source of definitions (ESPD convention).
_DEFAULT_DEFINITION_DOCS: tuple[str, ...] = ("technical_specification",)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _id_mode_title(content: str, id_end: int) -> str:
    """Best-effort title for a bare-id definition: the text following the id on
    its logical line. Handles longtable rows (``id & cell & ...`` -> first cell)
    and inline forms (``id - text`` -> text after a separator)."""
    line = re.split(r"\\\\|\n", content[id_end:], maxsplit=1)[0].strip()
    if line.startswith("&"):
        cells = line.split("&")
        return _clean_text(cells[1]) if len(cells) > 1 else ""
    return _clean_text(re.sub(r"^[\s—–:\-]+", "", line))


class CompiledRequirementFormat:
    """Pre-compiled definition/reference matchers for one resolved format."""

    def __init__(
        self,
        kind: RequirementFormatKind,
        *,
        def_re: re.Pattern[str] | None,
        ref_re: re.Pattern[str] | None,
        id_re: re.Pattern[str] | None,
        definition_docs: frozenset[str],
    ) -> None:
        self._kind = kind
        self._def_re = def_re
        self._ref_re = ref_re
        self._id_re = id_re
        self._definition_docs = definition_docs

    def definitions(self, content: str, doc_id: str | None) -> Iterator[tuple[str, str]]:
        """Yield (requirement_id, title) for every definition found in content."""
        if self._kind is RequirementFormatKind.id:
            return self._id_definitions(content, doc_id)
        return self._pattern_definitions(content)

    def references(self, content: str, doc_id: str | None) -> Iterator[str]:
        """Yield referenced requirement ids found in content."""
        if self._kind is RequirementFormatKind.id:
            return self._id_references(content, doc_id)
        return self._pattern_references(content)

    def _is_definition_doc(self, doc_id: str) -> bool:
        # `definition_docs` в паке — id ОПРЕДЕЛЕНИЙ; в team сюда приходят id
        # инстансов ("tz--shalaev") — сравниваем по базовой части.
        return doc_id in self._definition_docs or split_instance_id(doc_id)[0] in self._definition_docs

    def _id_definitions(self, content: str, doc_id: str | None) -> Iterator[tuple[str, str]]:
        id_re = self._id_re
        if id_re is None or doc_id is None or not self._is_definition_doc(doc_id):
            return
        for m in id_re.finditer(content):
            rid = (m.groupdict().get("id") or m.group(0)).strip()
            if rid:
                yield rid, _id_mode_title(content, m.end())

    def _pattern_definitions(self, content: str) -> Iterator[tuple[str, str]]:
        def_re = self._def_re
        if def_re is None:
            return
        for m in def_re.finditer(content):
            rid = m.group("id").strip()
            if rid:
                yield rid, _clean_text(m.groupdict().get("title") or "")

    def _id_references(self, content: str, doc_id: str | None) -> Iterator[str]:
        id_re = self._id_re
        if id_re is None or doc_id is None or self._is_definition_doc(doc_id):
            return
        for m in id_re.finditer(content):
            rid = (m.groupdict().get("id") or m.group(0)).strip()
            if rid:
                yield rid

    def _pattern_references(self, content: str) -> Iterator[str]:
        ref_re = self._ref_re
        if ref_re is None:
            return
        use_group = "ids" in ref_re.groupindex
        for m in ref_re.finditer(content):
            raw = m.group("ids") if use_group else m.group(0)
            for rid in (raw or "").split(","):
                cleaned = rid.strip()
                if cleaned:
                    yield cleaned


class RequirementMatchingService:
    """Builds a CompiledRequirementFormat from a RequirementsFormat.

    Validates user-supplied patterns and raises ValueError on misconfiguration
    (invalid regex, missing required fields/groups) so callers can surface a
    clear message instead of crashing the scan.
    """

    def compile(self, fmt: RequirementsFormat) -> CompiledRequirementFormat:
        if fmt.kind is RequirementFormatKind.macro:
            return CompiledRequirementFormat(
                fmt.kind,
                def_re=re.compile(_MACRO_DEF_PATTERN),
                ref_re=re.compile(_MACRO_REF_PATTERN),
                id_re=None,
                definition_docs=frozenset(),
            )
        en = current_interface_language() is Lang.en
        if fmt.kind is RequirementFormatKind.id:
            if not fmt.id_pattern:
                raise ValueError(
                    "The «id» format requires id_pattern (a regex for the requirement identifier)."
                    if en
                    else "Формат «id» требует id_pattern (regex идентификатора требования)."
                )
            docs = frozenset(fmt.definition_docs) or frozenset(_DEFAULT_DEFINITION_DOCS)
            return CompiledRequirementFormat(
                fmt.kind,
                def_re=None,
                ref_re=None,
                id_re=self._compile(fmt.id_pattern, "id_pattern"),
                definition_docs=docs,
            )
        if not fmt.def_pattern or not fmt.ref_pattern:
            raise ValueError(
                "The «custom» format requires def_pattern and ref_pattern."
                if en
                else "Формат «custom» требует def_pattern и ref_pattern."
            )
        def_re = self._compile(fmt.def_pattern, "def_pattern")
        if "id" not in def_re.groupindex:
            raise ValueError(
                "def_pattern must contain a named group (?P<id>...)."
                if en
                else "def_pattern должен содержать именованную группу (?P<id>...)."
            )
        return CompiledRequirementFormat(
            fmt.kind,
            def_re=def_re,
            ref_re=self._compile(fmt.ref_pattern, "ref_pattern"),
            id_re=None,
            definition_docs=frozenset(),
        )

    @staticmethod
    def _compile(pattern: str, field_name: str) -> re.Pattern[str]:
        try:
            return re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            msg = (
                f"Invalid regex in {field_name}: {exc}"
                if current_interface_language() is Lang.en
                else f"Некорректный regex в {field_name}: {exc}"
            )
            raise ValueError(msg) from exc
