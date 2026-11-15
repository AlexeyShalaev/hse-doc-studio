"""Черновик заметок к версии из отчёта классификатора (docs/design/template-studio.md, 7.4; срез T10).

Причины отчёта (`core/template_diff.ChangeReport`) группируются по коду и превращаются в пункты по шаблонам фраз,
парами ru и en (списки `changes` параллельны, это проверяет `pack_lint`). Сущность берётся из пути причины и
называется так, как её видит человек: поле по подписи `label`, документ по названию, слот подписи по подписи,
профиль сдачи по названию; без подписи остаётся id.

`breaking_changes` предлагается, если классификатор нашёл сужение: удаление, ужесточение требования, смену типа
поля, способы подписи пункта.

Это черновик: автор правит пункты, перевод en по кнопке через ИИ-провайдера не входит в срез.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from hse_doc_studio.core.template_diff import ChangeReason, ChangeReport, VersionSnapshot

LANGS = ("ru", "en")
_MAX_NAMES = 6
_MAX_ITEMS = 12

# Коды, которые означают сужение: их предлагается перечислить в `breaking_changes`.
BREAKING_CODES = frozenset({"removed", "item_removed", "required_stricter", "slot_required", "field_type", "methods"})

_FIELD = re.compile(r"^meta_fields\.([^.\[]+)")
_SLOT = re.compile(r"^signatures\.slots\[([^\]]+)\]")
_DOC = re.compile(r"^documents\[([^\]]+)\]")
_PROFILE = re.compile(r"^pack_submission\.profiles\[([^\]]+)\]")
_ITEM = re.compile(r"^pack_submission\.profiles\[[^\]]+\]\.items\[([^\]]+)\]")
_GROUP = re.compile(r"^meta_groups\[([^\]]+)\]")
_FORM = re.compile(r"^forms\[([^\]]+)\]")
_CHECKS = re.compile(r"^checks\[([^\]]+)\](?:\.rules\[([^\]]+)\])?")
_FILE_DOC = re.compile(r"^files/([^/]+)/")

# Код -> (ru, en). `{names}` перечисление сущностей; без сущностей берётся вариант из `_PLAIN`.
_PHRASES: dict[str, tuple[str, str]] = {
    "signing_preset": (
        "Места подписей и метки даты заданы шаблоном: {names}.",
        "Signature places and date marks are preset by the template: {names}.",
    ),
    "deadline_hint": ("Подсказки сроков у точек сдачи: {names}.", "Deadline hints for checkpoints: {names}."),
    "text": ("Уточнены подписи и подсказки: {names}.", "Labels and hints are refined: {names}."),
    "presentation": ("Обновлено оформление: {names}.", "Appearance is updated: {names}."),
    "order": ("Изменён порядок: {names}.", "The order is changed: {names}."),
    "grouping": ("Изменены группы в интерфейсе: {names}.", "Interface groups are changed: {names}."),
    "file_changed": ("Исправлены файлы документов: {names}.", "Document files are fixed: {names}."),
    "document_source": ("Исправлены исходники документов: {names}.", "Document sources are fixed: {names}."),
    "file_added": ("Новые файлы в документах: {names}.", "New files in documents: {names}."),
    "document_file_added": ("Новые исходники документов: {names}.", "New document sources: {names}."),
    "file_removed": ("Удалены файлы: {names}.", "Removed files: {names}."),
    "check_tuning": ("Настроены проверки: {names}.", "Checks are tuned: {names}."),
    "check_rule_removed": ("Убраны правила проверок: {names}.", "Removed check rules: {names}."),
    "check_file_removed": ("Убраны файлы проверок: {names}.", "Removed check files: {names}."),
    "methods": ("Изменены способы подписи пунктов сдачи: {names}.", "Signing methods of checkpoint items: {names}."),
    "optional_field_added": ("Новые необязательные поля: {names}.", "New optional fields: {names}."),
    "field_added": ("Новые поля: {names}.", "New fields: {names}."),
    "field_default": (
        "Изменены значения по умолчанию или варианты полей: {names}.",
        "Field defaults or options are changed: {names}.",
    ),
    "required_looser": ("Ослаблены требования: {names}.", "Requirements are relaxed: {names}."),
    "required_stricter": ("Ужесточены требования: {names}.", "Requirements are tightened: {names}."),
    "field_type": ("Изменён тип полей: {names}.", "Field types are changed: {names}."),
    "document_added": ("Новые документы: {names}.", "New documents: {names}."),
    "group_added": ("Новые группы полей: {names}.", "New field groups: {names}."),
    "form_added": ("Новые анкеты: {names}.", "New forms: {names}."),
    "profile_added": ("Новые точки сдачи: {names}.", "New checkpoints: {names}."),
    "item_added": ("Новые пункты точек сдачи: {names}.", "New checkpoint items: {names}."),
    "slot_added": ("Новые подписи: {names}.", "New signatures: {names}."),
    "variant_added": ("Новые варианты документов: {names}.", "New document variants: {names}."),
    "check_rule_added": ("Новые правила проверок: {names}.", "New check rules: {names}."),
    "check_file_added": ("Новые файлы проверок: {names}.", "New check files: {names}."),
    "item_removed": ("Убраны пункты точек сдачи: {names}.", "Removed checkpoint items: {names}."),
    "item_signatures": ("Изменены подписи пунктов сдачи: {names}.", "Signatures of checkpoint items: {names}."),
    "extra_items": ("Изменён состав пакета сдачи: {names}.", "Submission package contents: {names}."),
    "slot_scope": ("Изменено, где нужны подписи: {names}.", "Where signatures apply: {names}."),
    "slot_required": ("Подписи стали обязательными: {names}.", "Signatures became required: {names}."),
    "document_scope": ("Изменены языки или состав документов: {names}.", "Document languages or scope: {names}."),
    "version_scope": ("Изменены языки, виды работы или состав авторов.", "Languages, work kinds or staffing changed."),
    "build_setup": ("Изменены настройки сборки: {names}.", "Build settings are changed: {names}."),
    "removed": ("Удалено: {names}.", "Removed: {names}."),
    "unclassified": ("Прочие изменения: {names}.", "Other changes: {names}."),
}

# Те же пункты без перечисления: сущности из пути не нашлось.
_PLAIN: dict[str, tuple[str, str]] = {
    "signing_preset": ("Порядок подписания задан шаблоном.", "The signing order is preset by the template."),
    "text": ("Уточнены тексты интерфейса.", "Interface texts are refined."),
    "presentation": ("Обновлено оформление.", "Appearance is updated."),
    "order": ("Изменён порядок элементов.", "The order of items is changed."),
    "grouping": ("Изменены группы в интерфейсе.", "Interface groups are changed."),
    "check_tuning": ("Настроены проверки.", "Checks are tuned."),
    "build_setup": ("Изменены настройки сборки.", "Build settings are changed."),
    "file_changed": ("Исправлены файлы шаблона.", "Template files are fixed."),
    "file_added": ("Новые файлы шаблона.", "New template files."),
}

# Порядок пунктов: сначала новое, затем исправления, в конце служебное.
_ORDER = (
    "document_added",
    "field_added",
    "optional_field_added",
    "group_added",
    "form_added",
    "profile_added",
    "item_added",
    "slot_added",
    "variant_added",
    "check_file_added",
    "check_rule_added",
    "document_file_added",
    "signing_preset",
    "deadline_hint",
    "methods",
    "item_signatures",
    "extra_items",
    "slot_scope",
    "slot_required",
    "required_stricter",
    "required_looser",
    "field_type",
    "field_default",
    "document_scope",
    "version_scope",
    "build_setup",
    "document_source",
    "file_changed",
    "file_added",
    "text",
    "presentation",
    "grouping",
    "order",
    "check_tuning",
    "check_rule_removed",
    "check_file_removed",
    "file_removed",
    "item_removed",
    "removed",
    "unclassified",
)


@dataclass(frozen=True)
class DraftNotes:
    changes: Mapping[str, tuple[str, ...]]
    breaking_changes: Mapping[str, tuple[str, ...]]


def _label(raw: Any, lang: str) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, Mapping):
        for key in (lang, "ru", "en"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _by_id(items: Any, wanted: str) -> Mapping[str, Any] | None:
    if isinstance(items, Mapping):
        found = items.get(wanted)
        return found if isinstance(found, Mapping) else None
    if isinstance(items, list):
        for item in items:
            if isinstance(item, Mapping) and str(item.get("id", item.get("doc_id", ""))) == wanted:
                return item
    return None


class _Names:
    """Подписи сущностей по снимку новой версии (базы, если сущность удалена)."""

    def __init__(self, snapshots: Iterable[VersionSnapshot]) -> None:
        self._snapshots = tuple(snapshots)

    def _first(self, pick: Any, lang: str, *keys: str) -> str | None:
        for snapshot in self._snapshots:
            entity = pick(snapshot)
            if entity is None:
                continue
            for key in keys:
                text = _label(entity.get(key), lang)
                if text:
                    return text
        return None

    def field(self, key: str, lang: str) -> str:
        found = self._first(lambda s: _by_id(s.manifest.get("meta_fields"), key), lang, "label")
        return found or key

    def slot(self, slot_id: str, lang: str) -> str:
        found = self._first(
            lambda s: _by_id((s.manifest.get("signatures") or {}).get("slots"), slot_id), lang, "label", "name"
        )
        return found or slot_id

    def document(self, doc_id: str, lang: str) -> str:
        found = self._first(lambda s: _doc(s, doc_id), lang, "name", "title", "short_name")
        return found or doc_id

    def check(self, file: str, rule: str | None, lang: str) -> str:
        if rule is None:
            found = self._first(
                lambda s: s.checks.get(file) if isinstance(s.checks.get(file), Mapping) else None, lang, "label"
            )
            return found or file.removesuffix(".yaml")
        found = self._first(
            lambda s: _by_id(
                (s.checks.get(file) or {}).get("rules") if isinstance(s.checks.get(file), Mapping) else None, rule
            ),
            lang,
            "title",
            "label",
        )
        return found or rule

    def profile(self, profile_id: str, lang: str) -> str:
        found = self._first(
            lambda s: _by_id((s.manifest.get("pack_submission") or {}).get("profiles"), profile_id),
            lang,
            "label",
            "name",
            "title",
        )
        return found or profile_id


def _doc(snapshot: VersionSnapshot, doc_id: str) -> Mapping[str, Any] | None:
    found = snapshot.documents.get(doc_id)
    return found if isinstance(found, Mapping) else None


def _quote(text: str, lang: str) -> str:
    return f"«{text}»" if lang == "ru" else f'"{text}"'


# Коды, у которых сущность без подписи не называется: пункт пишется без перечисления.
_UNNAMED = frozenset({"text", "presentation", "order", "grouping", "check_tuning", "build_setup", "signing_preset"})


def _file_doc(doc_id: str, names: _Names, lang: str) -> str:
    if doc_id == "common":
        return "общие файлы" if lang == "ru" else "common files"
    return _quote(names.document(doc_id, lang), lang)


def _entity(reason: ChangeReason, names: _Names, lang: str) -> str | None:
    """Как назвать сущность причины: по подписи из манифеста, иначе id; None, если называть нечего."""
    path = reason.path
    namers: tuple[tuple[re.Pattern[str], Any], ...] = (
        (_ITEM, lambda m: m.group(1)),
        (_FIELD, lambda m: _quote(names.field(m.group(1), lang), lang)),
        (_SLOT, lambda m: _quote(names.slot(m.group(1), lang), lang)),
        (_DOC, lambda m: _quote(names.document(m.group(1), lang), lang)),
        (_PROFILE, lambda m: _quote(names.profile(m.group(1), lang), lang)),
        (_FILE_DOC, lambda m: _file_doc(m.group(1), names, lang)),
        (_CHECKS, lambda m: _quote(names.check(m.group(1), m.group(2), lang), lang)),
        (_GROUP, lambda m: m.group(1)),
        (_FORM, lambda m: m.group(1)),
    )
    for pattern, name in namers:
        if match := pattern.match(path):
            return str(name(match))
    unnamed = reason.code in _UNNAMED or (reason.code in {"file_changed", "file_added"} and path.startswith("files/"))
    return None if unnamed else path


def _phrase(code: str, index: int, entities: list[str]) -> str:
    lang = LANGS[index]
    phrase = _PHRASES.get(code, _PHRASES["unclassified"])[index]
    if entities:
        tail = "" if len(entities) <= _MAX_NAMES else (" и другие" if lang == "ru" else " and more")
        return phrase.format(names=", ".join(entities[:_MAX_NAMES]) + tail)
    if code in _PLAIN:
        return _PLAIN[code][index]
    return phrase.replace(": {names}", "")


def _items(reasons: Iterable[ChangeReason], names: _Names) -> dict[str, tuple[str, ...]]:
    groups: dict[str, dict[str, list[str]]] = {}
    for reason in reasons:
        bucket = groups.setdefault(reason.code, {lang: [] for lang in LANGS})
        for lang in LANGS:
            entity = _entity(reason, names, lang)
            if entity is not None and entity not in bucket[lang]:
                bucket[lang].append(entity)
    rank = {code: index for index, code in enumerate(_ORDER)}
    ordered = sorted(groups, key=lambda c: rank.get(c, len(rank)))
    return {
        lang: tuple(_phrase(code, index, groups[code][lang]) for code in ordered)[:_MAX_ITEMS]
        for index, lang in enumerate(LANGS)
    }


def draft_notes(report: ChangeReport, new: VersionSnapshot, base: VersionSnapshot | None = None) -> DraftNotes:
    """Пункты `changes` и `breaking_changes` (ru и en параллельно) по причинам отчёта."""
    names = _Names([new, *([base] if base is not None else [])])
    changes = _items(report.reasons, names)
    breaking = _items((r for r in report.reasons if r.code in BREAKING_CODES), names)
    return DraftNotes(changes=changes, breaking_changes=breaking)
