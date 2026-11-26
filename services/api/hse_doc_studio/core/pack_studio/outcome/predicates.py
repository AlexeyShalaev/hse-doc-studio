"""Закрытые предикаты версии шаблона в одном месте: документ есть в проекте, активен ли он, пункт точки сдаётся,
поле анкеты видно, как называется итоговый файл.

Раньше каждое такое условие было написано заново рядом с тем, что его читает (план подписей, пакет сдачи, форма
анкеты, настройки проекта, предпросмотр). Вычислитель результата (`docs/design/template-studio-outcome.md`, 4.1) зовёт
эти функции, а старые места ссылаются сюда же, поэтому результат и движок не расходятся по построению.

Модуль чистый и лёгкий: без доступа к файлам, часам и случайности, без импорта слоёв выше core.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING, Any

from hse_doc_studio.core.enums import ProjectKind

if TYPE_CHECKING:
    from hse_doc_studio.core.catalog import DocumentDefinition, VisibleIf

# Расписка NDA как документ: есть в комплекте, только пока в проекте включено `meta.nda`.
NDA_DOC_ID = "nda"

# Руководства (программиста и оператора): мета `manuals` (select, scope=author) говорит, какие из них входят в
# комплект. Правило зашито в движок (R4 дизайна результата): подстрока варианта выбора, русская по сегодняшнему паку.
MANUAL_MARKERS: Mapping[str, str] = {"programmer_manual": "программиста", "operator_manual": "оператора"}
MANUAL_DEF_IDS: frozenset[str] = frozenset(MANUAL_MARKERS)

# Виды работы: условие `supported_kinds` ограничивает, только если не перечисляет оба.
ALL_KINDS: frozenset[str] = frozenset(kind.value for kind in ProjectKind)

# Режимы состава у документов и проекта (`supported_staffing`): один автор и команда.
STAFFING_SOLO = "solo"
STAFFING_TEAM = "team"

# Документ с выбором варианта при создании проекта (`pres_variant`): остальным достаётся первый вариант.
PRESENTATION_DEF_ID = "presentation"


# ── Вид работы и состав ──────────────────────────────────────────────────────


def kind_allowed(supported_kinds: Collection[str], kind: str) -> bool:
    """Вид работы входит в `supported_kinds` документа, пункта, анкеты или файла сверх документов."""
    return kind in supported_kinds


def field_visible_for_kind(supported_kinds: Collection[str], kind: str) -> bool:
    """Поле проекта показывается в этом виде работы; пустой список значит «во всех» (как `metaFieldVisibleForKind`)."""
    return not supported_kinds or kind in supported_kinds


def kinds_restrict(supported_kinds: Collection[str]) -> bool:
    """Список видов что-то исключает (не пуст и не называет оба вида): только такие условия попадают в трассу."""
    return bool(supported_kinds) and not set(supported_kinds) >= ALL_KINDS


def staffing_allowed(supported_staffing: Collection[str], staffing: str) -> bool:
    """Режим состава (`solo` или `team`) входит в `supported_staffing` документа."""
    return staffing in supported_staffing


def document_in_scope(
    supported_kinds: Collection[str], supported_staffing: Collection[str], kind: str, staffing: str
) -> bool:
    """Документ есть в проекте этого вида работы и состава (как `create_project._build_documents`)."""
    return kind_allowed(supported_kinds, kind) and staffing_allowed(supported_staffing, staffing)


# ── NDA и руководства ────────────────────────────────────────────────────────


def nda_enabled(meta: Mapping[str, Any]) -> bool:
    """В проекте включено NDA (`meta.nda`)."""
    return bool(meta.get("nda"))


def manual_selected(selection: str, def_id: str) -> bool:
    """Руководство `def_id` входит в комплект при выбранном значении `manuals`.

    Выбор не задан или не называет ни одного руководства: входят оба («минимум одно» гарантировано).
    """
    lowered = selection.lower()
    if not lowered:
        return True
    chosen = {doc_id for doc_id, marker in MANUAL_MARKERS.items() if marker in lowered}
    return def_id in (chosen or MANUAL_DEF_IDS)


# ── Пункты точки сдачи ───────────────────────────────────────────────────────


def item_off_reason(
    *,
    skip_if_nda: bool,
    item_kinds: Collection[str],
    kind: str,
    nda: bool,
    doc_state: str,
) -> str | None:
    """Почему пункт не сдаётся в этой комбинации; None: сдаётся.

    Порядок причин тот же, что в проверке пакета: NDA (`skip_if_nda` при включённом NDA), вид работы пункта, затем
    документа нет в комплекте (`absent`: вид работы или состав) или он выключен (`inactive`: NDA или руководства).
    """
    if skip_if_nda and nda:
        return "nda"
    if not kind_allowed(item_kinds, kind):
        return "kind"
    if doc_state in ("absent", "inactive"):
        return doc_state
    return None


def item_skipped(*, skip_if_nda: bool, item_kinds: Collection[str], kind: str, nda: bool) -> bool:
    """Пункт выпадает из пакета по NDA или виду работы, ещё до вопроса, есть ли документ."""
    return (
        item_off_reason(skip_if_nda=skip_if_nda, item_kinds=item_kinds, kind=kind, nda=nda, doc_state="active")
        is not None
    )


# ── Анкеты ───────────────────────────────────────────────────────────────────


def visible_if_held(condition: VisibleIf | None, answers: Mapping[str, Any]) -> bool:
    """Поле анкеты видно: условия нет или ответ на `field` равен `equals` (единственный примитив движка)."""
    if condition is None:
        return True
    return bool(answers.get(condition.field) == condition.equals)


# ── Варианты и имена файлов ──────────────────────────────────────────────────


def chosen_variant_id(doc_def: DocumentDefinition, requested: str | None) -> str | None:
    """Вариант документа при создании проекта: `requested` у презентации (если он есть), иначе первый.

    Без вариантов None."""
    if not doc_def.variants:
        return None
    if requested and doc_def.id == PRESENTATION_DEF_ID:
        ids = [variant.id for variant in doc_def.variants]
        return requested if requested in ids else doc_def.variants[0].id
    return doc_def.variants[0].id


def variant_available(supported_langs: Collection[str], lang: str) -> bool:
    """Вариант документа доступен при этом языке проекта; пустой список значит «во всех языках»."""
    return not supported_langs or lang in supported_langs


def resolve_output_names(doc_def: DocumentDefinition, chosen_variant: str | None) -> dict[str, str]:
    """Имена итогового файла по языкам: у вариантного документа из ВЫБРАННОГО варианта, иначе с уровня документа."""
    if doc_def.variants:
        variant = next((v for v in doc_def.variants if v.id == chosen_variant), doc_def.variants[0])
        if variant.output_name:
            return variant.output_name
    return doc_def.output_name


def output_arcname(names: Mapping[str, str], lang: str, output_file: str) -> str:
    """Имя итогового файла для языка проекта: его язык, иначе русский, иначе имя файла сборки."""
    return names.get(lang, names.get("ru", output_file))


def _is_initial(word: str) -> bool:
    """«I.», «A.D.» или одна буква: инициал, а не фамилия."""
    return "." in word or len(word) == 1


def owner_short_name(full_name: str, slug: str | None, lang: str = "ru") -> str:
    """Короткое имя владельца личного документа команды: фамилия из ФИО, без имени слаг.

    В русском проекте ФИО пишут «Фамилия Имя Отчество»: фамилия это первое слово. В английском проекте имя пишут
    «Given Surname» (как автонаборы предпросмотра, «Ivan Ivanov»): фамилия это последнее слово, инициалы не в счёт
    («Ivan I. Ivanov», «Ivanov I.»); «Surname, Given» читается по запятой. ФИО кириллицей в английском проекте
    записано по-русски, фамилия в нём первая."""
    parts = full_name.split()
    if not parts:
        return slug or ""
    if lang != "en" or any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in full_name):
        return parts[0]
    if parts[0].endswith(",") and len(parts[0]) > 1:
        return parts[0].rstrip(",")
    words = [word for word in parts if not _is_initial(word)]
    return words[-1] if words else parts[0]


def with_owner_suffix(arcname: str, owner_name: str | None) -> str:
    """Личный документ в командном пакете несёт фамилию владельца в имени файла."""
    if not owner_name:
        return arcname
    stem, ext = arcname.rsplit(".", 1) if "." in arcname else (arcname, "")
    return f"{stem} — {owner_name}.{ext}" if ext else f"{stem} — {owner_name}"
