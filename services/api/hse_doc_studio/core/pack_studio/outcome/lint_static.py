"""Статические правила линтера результата (раздел 6.1 дизайна, срез O8): читают версию и сырые тексты манифестов.

Ни расчёта результата, ни перебора комбинаций: правила работают мгновенно и поэтому входят в общий список «Проблемы»
Студии при каждой проверке версии. Что видно только на комбинациях вводных (слот назван, но условия не пускают;
документ не активен ни в одной строке атласа; шаг ждёт человека, которого нет), ловят правила по атласу
(`lint_atlas.py`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from hse_doc_studio.core.catalog import FormFieldDef, TemplateVersion
from hse_doc_studio.core.enums import FormFieldType, RequiredAt
from hse_doc_studio.core.meta_usage import PERSON_KEYS
from hse_doc_studio.core.pack_studio.outcome.lint import (
    VERSION_MANIFEST,
    LintFinding,
    LintSources,
    Witness,
    doc_manifest,
    finding,
    limit_per_rule,
    with_lines,
)
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef
from hse_doc_studio.core.pack_studio.outcome.predicates import ALL_KINDS, MANUAL_MARKERS, NDA_DOC_ID

type Rule = Callable[[LintSources], Iterable[LintFinding]]


# ── visible_if ───────────────────────────────────────────────────────────────


def _equals_text(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def _equals_problem(source: FormFieldDef, equals: Any) -> str | None:
    """Почему условие `equals` недостижимо у поля-источника; None: достижимо или проверить нельзя."""
    if source.type is FormFieldType.bool_:
        return None if isinstance(equals, bool) else "а у bool-поля ответ это true или false"
    if source.type is FormFieldType.select and source.options:
        ids = [option.id for option in source.options]
        if isinstance(equals, bool):
            return f"а у select-поля ответ это id варианта ({', '.join(ids)}), не логическое значение"
        if str(equals) not in ids:
            return f"а у поля есть только варианты {', '.join(ids)}"
    return None


def _form_fields(form: Any) -> dict[str, FormFieldDef]:
    found: dict[str, FormFieldDef] = {}
    for section in form.sections:
        for item in section.fields:
            found.setdefault(item.id, item)
    return found


def _visible_if_problem(
    form_id: str, item: FormFieldDef, fields: Mapping[str, FormFieldDef], base: str
) -> LintFinding | None:
    condition = item.visible_if
    if condition is None:
        return None
    element = ElementRef("forms", f"{form_id}/{item.id}")
    source = fields.get(condition.field)
    if source is None:
        return finding(
            "visible-if-unknown-field",
            "error",
            f"Поле «{item.id}» анкеты «{form_id}» видно по ответу на «{condition.field}», а такого поля в анкете "
            "нет: поле не станет видимым никогда.",
            "Укажите id существующего поля той же анкеты в visible_if.field или уберите условие.",
            VERSION_MANIFEST,
            f"{base}/field",
            element,
        )
    problem = _equals_problem(source, condition.equals)
    if problem is None:
        return None
    return finding(
        "visible-if-value-not-in-options",
        "error",
        f"Поле «{item.id}» анкеты «{form_id}»: условие visible_if ждёт {_equals_text(condition.equals)} от "
        f"«{condition.field}», {problem}. Поле не станет видимым никогда.",
        "Возьмите значение из options поля-источника (строкой в кавычках: yes и no без кавычек YAML читает как true "
        "и false) или true и false у bool-поля.",
        VERSION_MANIFEST,
        f"{base}/equals",
        element,
    )


def _visible_if_rules(sources: LintSources) -> Iterable[LintFinding]:
    for form_index, form in enumerate(sources.version.forms):
        fields = _form_fields(form)
        for section_index, section in enumerate(form.sections):
            for field_index, item in enumerate(section.fields):
                base = f"/forms/{form_index}/sections/{section_index}/fields/{field_index}/visible_if"
                found = _visible_if_problem(form.id, item, fields, base)
                if found is not None:
                    yield found


# ── Обязательные и недоступные поля ──────────────────────────────────────────


def version_kinds(version: TemplateVersion) -> set[str]:
    """Виды работы, которые версия порождает: объединение `supported_kinds` документов."""
    kinds = {kind for doc in version.documents for kind in doc.supported_kinds} & ALL_KINDS
    return kinds or {"research"}


def _required_hidden_rules(sources: LintSources) -> Iterable[LintFinding]:
    """Поле или анкета обязательны, а их `supported_kinds` не называет ни одного вида работы версии: поле скрыто в
    каждой комбинации, заполнить его нельзя (остальные случаи ловит атлас)."""
    version = sources.version
    kinds = version_kinds(version)
    for key, meta in version.meta_fields.items():
        if meta.required_at is not RequiredAt.never and meta.supported_kinds and not set(meta.supported_kinds) & kinds:
            yield finding(
                "required-hidden",
                "error",
                f"Поле проекта «{key}» обязательно (required_at: {meta.required_at.value}), но его supported_kinds "
                f"({', '.join(meta.supported_kinds)}) не содержит ни одного вида работы версии "
                f"({', '.join(sorted(kinds))}): поле скрыто всегда, заполнить его нельзя.",
                "Исправьте supported_kinds поля (research, project) или поставьте required_at: never.",
                VERSION_MANIFEST,
                f"/meta_fields/{key}",
                ElementRef("meta", key),
            )
    for index, form in enumerate(version.forms):
        required = [i.id for s in form.sections for i in s.fields if i.required]
        if required and form.supported_kinds and not set(form.supported_kinds) & kinds:
            yield finding(
                "required-hidden",
                "error",
                f"Анкета «{form.id}» не применима ни к одному виду работы версии, а её поля "
                f"({', '.join(required[:4])}) обязательны: заполнить их нельзя.",
                "Исправьте supported_kinds анкеты или снимите required у её полей.",
                VERSION_MANIFEST,
                f"/forms/{index}",
                ElementRef("forms", form.id),
            )


# ── Языки ────────────────────────────────────────────────────────────────────


def _lang_rules(sources: LintSources) -> Iterable[LintFinding]:
    version = sources.version
    langs = set(version.langs)
    if not langs:
        return
    for doc in version.documents:
        element = ElementRef("documents", doc.id)
        outside = [lang for lang in doc.supported_langs if lang not in langs]
        if outside:
            yield finding(
                "variant-lang-outside-langs",
                "error",
                f"Документ «{doc.id}»: supported_langs называет {', '.join(outside)}, а языки версии "
                f"{', '.join(version.langs)}: для этих языков документ недоступен.",
                "Добавьте язык в langs версии (и файлы редакции) или уберите его из supported_langs.",
                doc_manifest(doc.id),
                "/supported_langs",
                element,
            )
        for index, variant in enumerate(doc.variants):
            outside = [lang for lang in variant.supported_langs if lang not in langs]
            if outside:
                yield finding(
                    "variant-lang-outside-langs",
                    "error",
                    f"Вариант «{variant.id}» документа «{doc.id}»: supported_langs называет {', '.join(outside)}, а "
                    f"языки версии {', '.join(version.langs)}: вариант не станет доступен ни на одном языке.",
                    "Добавьте язык в langs версии или уберите его из supported_langs варианта.",
                    doc_manifest(doc.id),
                    f"/variants/{index}/supported_langs",
                    element,
                )


# ── NDA и руководства ────────────────────────────────────────────────────────


def _has_nda(version: TemplateVersion) -> bool:
    return (
        version.nda is not None
        or "nda" in version.meta_fields
        or any(doc.id == NDA_DOC_ID for doc in version.documents)
    )


def _nda_rules(sources: LintSources) -> Iterable[LintFinding]:
    version = sources.version
    if _has_nda(version):
        return
    for p_index, profile in enumerate(version.pack_submission.profiles):
        for i_index, item in enumerate(profile.items):
            if item.skip_if_nda:
                yield finding(
                    "skip-if-nda-without-nda",
                    "warning",
                    f"Пункт «{item.doc_id}» точки «{profile.id}» помечен skip_if_nda, а в версии нет NDA (ни блока "
                    "nda, ни поля nda, ни документа nda): пункт не выпадет никогда.",
                    "Добавьте NDA в версию или уберите skip_if_nda.",
                    VERSION_MANIFEST,
                    f"/pack_submission/profiles/{p_index}/items/{i_index}/skip_if_nda",
                    ElementRef("points", f"{profile.id}/{item.doc_id}"),
                )


def _manual_problem(version: TemplateVersion, def_id: str, marker: str) -> LintFinding | None:
    manuals = version.meta_fields.get("manuals")
    element = ElementRef("documents", def_id)
    if manuals is None:
        return finding(
            "builtin-gate-mismatch",
            "warning",
            f"Документ «{def_id}» в версии есть, а поля проекта manuals нет: правило движка manuals_gate читает его, "
            "выбирать руководства будет нечем, документ всегда в комплекте.",
            "Объявите поле manuals (select) в meta_fields или уберите документ.",
            VERSION_MANIFEST,
            "/meta_fields",
            element,
        )
    if manuals.options and not any(marker in str(option).lower() for option in manuals.options):
        return finding(
            "builtin-gate-mismatch",
            "warning",
            f"Ни один вариант поля manuals ({', '.join(map(str, manuals.options))}) не содержит слова «{marker}», по "
            f"которому движок включает документ «{def_id}»: выбор не сможет его выключить.",
            f"Назовите вариант так, чтобы в нём встречалось «{marker}» (регистр не важен).",
            VERSION_MANIFEST,
            "/meta_fields/manuals/options",
            element,
        )
    return None


def _nda_gate_problem(version: TemplateVersion) -> LintFinding | None:
    has_doc = any(doc.id == NDA_DOC_ID for doc in version.documents)
    has_switch = version.nda is not None or "nda" in version.meta_fields
    if has_doc and not has_switch:
        return finding(
            "builtin-gate-mismatch",
            "warning",
            "Документ «nda» в версии есть, а поля проекта nda и блока nda нет: правило движка nda_gate включает "
            "расписку только при включённом NDA, переключить его нечем, документ неактивен всегда.",
            "Объявите поле nda (bool) в meta_fields или уберите документ.",
            VERSION_MANIFEST,
            "/meta_fields",
            ElementRef("documents", NDA_DOC_ID),
        )
    if has_switch and not has_doc and version.nda is None:
        return finding(
            "builtin-gate-mismatch",
            "warning",
            "Поле проекта nda есть, а документа «nda» и блока nda в версии нет: включённое NDA ничего не добавит в "
            "комплект.",
            "Добавьте документ nda в documents или уберите поле.",
            VERSION_MANIFEST,
            "/meta_fields/nda",
            ElementRef("meta", "nda"),
        )
    return None


def _builtin_rules(sources: LintSources) -> Iterable[LintFinding]:
    """Зашитые правила движка (NDA, руководства) должны совпадать с манифестом: иначе документ тихо не работает."""
    version = sources.version
    doc_ids = {doc.id for doc in version.documents}
    for def_id, marker in MANUAL_MARKERS.items():
        problem = _manual_problem(version, def_id, marker) if def_id in doc_ids else None
        if problem is not None:
            yield problem
    nda = _nda_gate_problem(version)
    if nda is not None:
        yield nda


# ── Условия слотов ───────────────────────────────────────────────────────────


def _signing_entries(raw: Mapping[str, Any]) -> Iterable[tuple[int, str, int, Mapping[str, Any]]]:
    """Записи `signing_slots` сырого манифеста: индекс точки, её id, индекс записи и сама запись."""
    pack_submission = raw.get("pack_submission")
    profiles = pack_submission.get("profiles") if isinstance(pack_submission, dict) else None
    for p_index, profile in enumerate(profiles if isinstance(profiles, list) else []):
        entries = profile.get("signing_slots") if isinstance(profile, dict) else None
        for k, entry in enumerate(entries if isinstance(entries, list) else []):
            if isinstance(entry, dict):
                yield p_index, str(profile.get("id", p_index)), k, entry


def _when_problems(
    where: tuple[int, str, int], entry: Mapping[str, Any], catalog: set[str], docs: set[str]
) -> Iterable[LintFinding]:
    p_index, profile_id, k = where
    base = f"/pack_submission/profiles/{p_index}/signing_slots/{k}"
    element = ElementRef("route", f"{profile_id}/{entry.get('doc_id')}/{entry.get('slot_id')}")
    at = f"Точка «{profile_id}», запись {k + 1} signing_slots"
    when = entry.get("when")
    if isinstance(when, dict) and when.get("person") not in PERSON_KEYS:
        yield finding(
            "when-unknown-person",
            "error",
            f"{at}: when.person = {when.get('person')!r}, а персон три ({', '.join(PERSON_KEYS)}). Лоадер "
            "отбрасывает такую запись, слот не добавится.",
            "Укажите одну из персон: " + ", ".join(PERSON_KEYS) + ".",
            VERSION_MANIFEST,
            f"{base}/when/person",
            element,
        )
    if entry.get("slot_id") not in catalog:
        yield finding(
            "when-unknown-person",
            "error",
            f"{at}: слота {entry.get('slot_id')!r} нет в каталоге signatures.slots.",
            "Объявите слот в signatures.slots или поправьте slot_id.",
            VERSION_MANIFEST,
            f"{base}/slot_id",
            element,
        )
    if entry.get("doc_id") not in docs:
        yield finding(
            "when-unknown-person",
            "error",
            f"{at}: документа {entry.get('doc_id')!r} нет в ростере documents.",
            "Добавьте документ в documents или поправьте doc_id.",
            VERSION_MANIFEST,
            f"{base}/doc_id",
            element,
        )


def _when_rules(sources: LintSources) -> Iterable[LintFinding]:
    """`signing_slots[].when`: персона из трёх, слот из каталога, документ из ростера. Читает сырой манифест: запись с
    незнакомой персоной лоадер отбрасывает целиком, и в модели версии её уже нет."""
    version = sources.version
    catalog = {slot.id for slot in version.signatures_config.slots}
    docs = {doc.id for doc in version.documents}
    for p_index, profile_id, k, entry in _signing_entries(sources.raw_version()):
        yield from _when_problems((p_index, profile_id, k), entry, catalog, docs)


# ── Переводы ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Text:
    """Локализованный текст манифеста и где он лежит."""

    text: Mapping[str, str] | None
    what: str
    kind: str
    file: str
    pointer: str
    element: ElementRef | None


def _texts(version: TemplateVersion) -> Iterable[_Text]:
    for key, meta in version.meta_fields.items():
        element, where = ElementRef("meta", key), f"поля проекта «{key}»"
        base = f"/meta_fields/{key}"
        yield _Text(meta.label, where, "названия label", VERSION_MANIFEST, f"{base}/label", element)
        yield _Text(meta.help, where, "подсказки help", VERSION_MANIFEST, f"{base}/help", element)
    for f_index, form in enumerate(version.forms):
        form_element = ElementRef("forms", form.id)
        what, pointer = f"анкеты «{form.id}»", f"/forms/{f_index}/title"
        yield _Text(form.title, what, "названия title", VERSION_MANIFEST, pointer, form_element)
        for s_index, section in enumerate(form.sections):
            for i_index, item in enumerate(section.fields):
                base = f"/forms/{f_index}/sections/{s_index}/fields/{i_index}"
                element = ElementRef("forms", f"{form.id}/{item.id}")
                where = f"поля «{item.id}» анкеты «{form.id}»"
                if item.type is not FormFieldType.markdown:
                    yield _Text(item.label, where, "названия label", VERSION_MANIFEST, f"{base}/label", element)
                yield _Text(item.help, where, "подсказки help", VERSION_MANIFEST, f"{base}/help", element)
    yield from _document_texts(version)
    for index, slot in enumerate(version.signatures_config.slots):
        what = f"слота подписи «{slot.id}»"
        pointer = f"/signatures/slots/{index}/label"
        yield _Text(slot.label, what, "названия label", VERSION_MANIFEST, pointer, None)


def _document_texts(version: TemplateVersion) -> Iterable[_Text]:
    for doc in version.documents:
        element = ElementRef("documents", doc.id)
        yield _Text(doc.name, f"документа «{doc.id}»", "названия name", doc_manifest(doc.id), "/name", element)
        for index, variant in enumerate(doc.variants):
            what = f"варианта «{variant.id}» документа «{doc.id}»"
            pointer = f"/variants/{index}/label"
            yield _Text(variant.label, what, "названия label", doc_manifest(doc.id), pointer, element)


def _missing_langs(item: _Text, langs: tuple[str, ...]) -> list[str]:
    """Языки версии без перевода. Текст, которого нет совсем (подсказка не задана), не считается: это не пробел
    перевода."""
    if not item.text:
        return []
    return [lang for lang in langs if not str(item.text.get(lang, "")).strip()]


def _translation_rules(sources: LintSources) -> Iterable[LintFinding]:
    langs = sources.version.langs
    for item in _texts(sources.version):
        missing = _missing_langs(item, langs)
        if missing:
            yield finding(
                "translation-missing",
                "warning",
                f"У {item.what} нет перевода {item.kind} на {', '.join(missing)} (языки версии: {', '.join(langs)}).",
                f"Добавьте {item.kind} на {', '.join(missing)} или уберите язык из langs версии.",
                item.file,
                item.pointer,
                *([item.element] if item.element is not None else []),
            )


# ── Слоты ────────────────────────────────────────────────────────────────────


def named_slots(version: TemplateVersion) -> set[str]:
    """Слоты, названные хоть где-то в маршруте: подписи пунктов, `signing_slots`, порядок точек и версии."""
    named: set[str] = set()
    for step in version.signatures_config.route:
        named.update(step)
    for profile in version.pack_submission.profiles:
        for step in profile.signing_route:
            named.update(step)
        named.update(entry.slot_id for entry in profile.signing_slots)
        for item in profile.items:
            named.update(item.signatures)
    return named


def slot_never_routed(slot_id: str, index: int, *, named: bool, witnesses: tuple[Witness, ...] = ()) -> LintFinding:
    """Слот каталога, которого нет в маршруте: не назван нигде (`named=False`, статически) или назван, но ни одна
    комбинация вводных его не включает (по атласу)."""
    why = (
        "Слот назван в маршруте, но его условия и документы не пускают его ни при одной комбинации вводных."
        if named
        else "Слот не назван ни в подписях пунктов, ни в signing_slots, ни в порядке маршрута."
    )
    return LintFinding(
        "slot-never-routed",
        "warning",
        f"Слот «{slot_id}» не попадает в маршрут ни одной точки сдачи ни при какой комбинации вводных. {why}",
        "Добавьте слот в signatures пункта или в signing_slots точки либо удалите его из каталога signatures.slots.",
        VERSION_MANIFEST,
        f"/signatures/slots/{index}",
        None,
        (),
        witnesses,
    )


def _slot_static_rules(sources: LintSources) -> Iterable[LintFinding]:
    """Слот каталога, не названный нигде, в маршрут не попадёт: точное правило по атласу называет и те слоты, которые
    названы, но условия не пускают."""
    named = named_slots(sources.version)
    for index, slot in enumerate(sources.version.signatures_config.slots):
        if slot.id not in named:
            yield slot_never_routed(slot.id, index, named=False)


STATIC_RULES: tuple[Rule, ...] = (
    _visible_if_rules,
    _required_hidden_rules,
    _lang_rules,
    _nda_rules,
    _builtin_rules,
    _when_rules,
    _translation_rules,
    _slot_static_rules,
)


def static_findings(sources: LintSources) -> tuple[LintFinding, ...]:
    """Статические правила версии: мгновенно, без расчёта результата. Строки находок взяты из текстов манифестов."""
    found = [item for rule in STATIC_RULES for item in rule(sources)]
    return with_lines(limit_per_rule(found), sources.texts)
