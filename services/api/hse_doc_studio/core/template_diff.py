"""Класс новой версии шаблона по содержимому (docs/design/template-studio.md, 7.2).

`classify_change(base_dir, new_dir)` сравнивает два каталога версии одного шаблона и возвращает `ChangeReport`:
минимальный класс, предложенный класс и причины. Номер версии класс задаёт сам (`classify_update`), здесь считается,
чего требует содержимое.

Правила двух видов:

* жёсткое задаёт минимум: новая поверхность (документ, поле, профиль, пункт точки, слот, правило проверок, язык,
  окружение сборки) это minor, удаление тоже minor, а предлагается major, пока нет декларации миграции;
* мягкое только предлагает класс: автор может выпустить мягче предложенного, но не мягче минимума, и пишет
  объяснение в `release.note` (содержимое файлов, `methods` пункта, `default_placement` слота, значения полей по
  умолчанию, удалённый файл).

Исключение для patch (`core/template_versions.py`, signing-route.md, 15.10): заготовки подписания (`placements`,
`default_dates`, `signing_slots`, `signatures.route`, `signing_route`, `signatures.anchor_macros`) и подсказки сроков
(`deadline_hint`) это patch жёстко. Второе исключение, необязательное поле (`required_at: never`, без `default` и
`auto`), это мягкое правило с предложением patch: пустое поле не должно менять вывод, а это видно только по шаблону.

Чего правило не знает, то minor (`unclassified`): классификатор ошибается в строгую сторону.

Сравнение идёт по разобранному YAML (комментарии и выравнивание не влияют), документы по `doc.yaml` из ростера,
проверки по `checks/*.yaml`, остальное по байтам файлов (CRLF как LF, как в дайджесте выпуска).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from hse_doc_studio.core.enums import RequiredAt, TemplateUpdateClass
from hse_doc_studio.core.template_versions import classify_update, is_softer, stricter

ChangeKind = Literal["added", "removed", "changed", "reordered"]

_PATCH = TemplateUpdateClass.patch
_MINOR = TemplateUpdateClass.minor
_MAJOR = TemplateUpdateClass.major

DOC_MANIFEST = "doc.yaml"
VERSION_MANIFEST = "version.yaml"
# Мусор файловых менеджеров и интерпретатора: не содержимое версии (как в дайджесте выпуска).
_JUNK_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
_JUNK_DIRS = frozenset({"__pycache__"})

# Коды причин исключения patch (15.10): по ним мастер пишет «patch: только заготовки подписания».
EXCEPTION_CODES = frozenset({"signing_preset", "deadline_hint"})

# Ключи текста: подписи, подсказки, названия. Правка текста это исправление (patch).
_TEXT_KEYS = frozenset(
    {"label", "help", "placeholder", "description", "title", "name", "short_name", "code", "output_name", "message"}
)
_PRESENTATION_KEYS = frozenset({"icon", "accent_hue"})
_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$")
_REQUIRED_RANK = {RequiredAt.never: 0, RequiredAt.finalize: 1, RequiredAt.create: 2}


# ── причины и отчёт ──


_MESSAGES: dict[str, tuple[str, str]] = {
    "signing_preset": ("Заготовка подписания: {path}", "Signing preset: {path}"),
    "deadline_hint": ("Подсказка срока точки: {path}", "Checkpoint deadline hint: {path}"),
    "text": ("Текст: {path}", "Text: {path}"),
    "presentation": ("Оформление: {path}", "Appearance: {path}"),
    "order": ("Порядок: {path}", "Order: {path}"),
    "grouping": ("Группа в интерфейсе: {path}", "Interface group: {path}"),
    "file_changed": ("Изменён файл {path}", "Changed file {path}"),
    "file_added": ("Новый файл {path}", "New file {path}"),
    "file_removed": (
        "Удалён файл {path}: проекты, которые на него ссылаются, перестанут собираться",
        "Removed file {path}: projects that reference it will stop building",
    ),
    "document_source": ("Исходник документа: {path}", "Document source: {path}"),
    "document_file_added": ("Новый исходник документа {path}", "New document source {path}"),
    "check_tuning": ("Настройка проверок: {path}", "Check tuning: {path}"),
    "check_rule_removed": ("Удалено правило проверок {path}", "Removed check rule {path}"),
    "check_file_removed": ("Удалён файл проверок {path}", "Removed check file {path}"),
    "methods": (
        "Способы подписи пункта точки: {path}; patch только с объяснением в release.note",
        "Signing methods of a checkpoint item: {path}; patch only with an explanation in release.note",
    ),
    "default_placement": (
        "Место подписи слота по умолчанию: {path}; patch только с объяснением в release.note",
        "Default signature place of a slot: {path}; patch only with an explanation in release.note",
    ),
    "optional_field_added": (
        "Новое необязательное поле {path}: patch, если пустое поле не меняет вывод, иначе minor",
        "New optional field {path}: patch when the empty field keeps the output, otherwise minor",
    ),
    "field_default": ("Значение поля по умолчанию или варианты: {path}", "Field default or options: {path}"),
    "required_looser": ("Требование ослаблено: {path}", "Requirement relaxed: {path}"),
    "required_stricter": ("Требование ужесточено: {path}", "Requirement tightened: {path}"),
    "field_type": ("Тип поля: {path}", "Field type: {path}"),
    "document_added": ("Новый документ {path}", "New document {path}"),
    "field_added": ("Новое поле {path}", "New field {path}"),
    "group_added": ("Новая группа полей {path}", "New field group {path}"),
    "form_added": ("Новая анкета {path}", "New form {path}"),
    "profile_added": ("Новый профиль сдачи {path}", "New submission profile {path}"),
    "item_added": ("Новый пункт точки {path}", "New checkpoint item {path}"),
    "slot_added": ("Новый слот подписи {path}", "New signature slot {path}"),
    "variant_added": ("Новый вариант документа {path}", "New document variant {path}"),
    "check_rule_added": ("Новое правило проверок {path}", "New check rule {path}"),
    "check_file_added": ("Новый файл проверок {path}", "New check file {path}"),
    "item_removed": ("Удалён пункт точки {path}", "Removed checkpoint item {path}"),
    "item_signatures": ("Подписи пункта точки: {path}", "Signatures of a checkpoint item: {path}"),
    "extra_items": ("Состав пакета сдачи: {path}", "Submission package contents: {path}"),
    "slot_scope": ("Применимость слота подписи: {path}", "Signature slot scope: {path}"),
    "slot_required": ("Слот подписи стал обязательным: {path}", "Signature slot became required: {path}"),
    "document_scope": ("Состав или языки документа: {path}", "Document scope or languages: {path}"),
    "version_scope": ("Языки, виды работы или состав авторов: {path}", "Languages, work kinds or staffing: {path}"),
    "build_setup": ("Сборка и окружение: {path}", "Build setup: {path}"),
    "removed": (
        "Удалено {path}: нужна декларация миграции данных, пока её нет, это major или отказ от удаления",
        "Removed {path}: needs a data migration declaration; until there is one, this is major or keep it",
    ),
    "unclassified": ("Изменение без правила классификатора: {path}", "Change without a classifier rule: {path}"),
}

# Короткие подписи кодов для бейджа «patch: заготовки подписания, файлы шаблона».
_SHORT: dict[str, tuple[str, str]] = {
    "signing_preset": ("заготовки подписания", "signing presets"),
    "deadline_hint": ("подсказки сроков", "deadline hints"),
    "text": ("тексты", "texts"),
    "presentation": ("оформление", "appearance"),
    "order": ("порядок", "order"),
    "grouping": ("группы интерфейса", "interface groups"),
    "file_changed": ("файлы шаблона", "template files"),
    "file_added": ("новые файлы", "new files"),
    "file_removed": ("удалённые файлы", "removed files"),
    "document_source": ("исходники документов", "document sources"),
    "check_tuning": ("настройка проверок", "check tuning"),
    "check_rule_removed": ("удалённые правила проверок", "removed check rules"),
    "check_file_removed": ("удалённые файлы проверок", "removed check files"),
    "methods": ("способы подписи", "signing methods"),
    "default_placement": ("места подписей по умолчанию", "default signature places"),
    "optional_field_added": ("необязательные поля", "optional fields"),
    "field_default": ("значения полей по умолчанию", "field defaults"),
    "required_looser": ("ослабленные требования", "relaxed requirements"),
    "removed": ("удаления", "removals"),
    "unclassified": ("изменения без правила", "unclassified changes"),
}

_RULE_WORDS = {
    ("ru", True): "жёсткое",
    ("ru", False): "мягкое",
    ("en", True): "hard",
    ("en", False): "soft",
}


def _lang_index(lang: str) -> int:
    return 1 if lang == "en" else 0


@dataclass(frozen=True)
class ChangeReason:
    """Одна причина класса: что изменилось (`path`), по какому правилу (`code`) и какой класс оно требует."""

    code: str
    path: str
    change: ChangeKind
    minimum: TemplateUpdateClass
    suggested: TemplateUpdateClass
    hard: bool

    @property
    def exception(self) -> bool:
        """Входит ли причина в исключение patch (заготовки подписания и подсказки сроков)."""
        return self.code in EXCEPTION_CODES

    def message(self, lang: str = "ru") -> str:
        template = _MESSAGES.get(self.code, _MESSAGES["unclassified"])[_lang_index(lang)]
        return template.format(path=self.path)

    def short(self, lang: str = "ru") -> str:
        labels = _SHORT.get(self.code)
        if labels is not None:
            return labels[_lang_index(lang)]
        template = _MESSAGES.get(self.code, _MESSAGES["unclassified"])[_lang_index(lang)]
        return template.split(" {path}", 1)[0].split(":", 1)[0].lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "change": self.change,
            "minimum": self.minimum.value,
            "suggested": self.suggested.value,
            "hard": self.hard,
            "exception": self.exception,
            "message": {"ru": self.message("ru"), "en": self.message("en")},
        }


@dataclass(frozen=True)
class ChangeReport:
    """Класс изменения по содержимому: минимум по всем причинам и предложение с мягкими правилами."""

    base_version: str | None
    new_version: str | None
    reasons: tuple[ChangeReason, ...]

    @property
    def minimum(self) -> TemplateUpdateClass:
        """Не мягче этого класса новую версию выпустить нельзя (жёсткие правила; у мягких минимум patch)."""
        result = _PATCH
        for reason in self.reasons:
            result = stricter(result, reason.minimum) or result
        return result

    @property
    def suggested(self) -> TemplateUpdateClass:
        """Класс с учётом мягких правил: его предлагает мастер, мягче можно только с объяснением автора."""
        result = self.minimum
        for reason in self.reasons:
            result = stricter(result, reason.suggested) or result
        return result

    @property
    def by_number(self) -> TemplateUpdateClass | None:
        """Класс по номерам версий; None, если номера не разобраны или новая не выше базы."""
        if self.base_version is None or self.new_version is None:
            return None
        return classify_update(self.base_version, self.new_version)

    @property
    def exception_only(self) -> bool:
        """Изменения только в ключах исключения patch (без файлов и прочего)."""
        return all(reason.exception for reason in self.reasons)

    def above(self, declared: TemplateUpdateClass) -> tuple[ChangeReason, ...]:
        """Причины, которые требуют больше, чем `declared` (по минимуму)."""
        return tuple(reason for reason in self.reasons if is_softer(declared, reason.minimum))

    def suggested_above(self, declared: TemplateUpdateClass) -> tuple[ChangeReason, ...]:
        """Мягкие причины, которые предлагают больше, чем `declared`."""
        return tuple(reason for reason in self.reasons if is_softer(declared, reason.suggested))

    def headline(self, lang: str = "ru") -> str:
        """Строка бейджа мастера: «patch: заготовки подписания, файлы шаблона»."""
        if not self.reasons:
            return f"{self.suggested.value}: " + ("изменений нет" if lang != "en" else "no changes")
        order = sorted(self.reasons, key=lambda r: (_rank(r.suggested), _rank(r.minimum)), reverse=True)
        labels = list(dict.fromkeys(reason.short(lang) for reason in order))
        return f"{self.suggested.value}: " + ", ".join(labels)

    def render(self, lang: str = "ru") -> str:
        """Отчёт для человека: класс, номер и причины списком."""
        en = lang == "en"
        lines = [self.headline(lang)]
        head = "Minimum {0}, suggested {1}" if en else "Минимум {0}, предлагается {1}"
        lines.append(head.format(self.minimum.value, self.suggested.value))
        if self.by_number is not None:
            word = "By number" if en else "По номеру"
            lines.append(f"{word} {self.base_version} > {self.new_version}: {self.by_number.value}")
        for reason in self.reasons:
            cls = reason.minimum.value
            if reason.suggested != reason.minimum:
                cls += (", suggested " if en else ", предлагается ") + reason.suggested.value
            lines.append(f"- [{cls}; {_RULE_WORDS[('en' if en else 'ru', reason.hard)]}] {reason.message(lang)}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_version": self.base_version,
            "new_version": self.new_version,
            "minimum": self.minimum.value,
            "suggested": self.suggested.value,
            "by_number": self.by_number.value if self.by_number else None,
            "exception_only": self.exception_only,
            "headline": {"ru": self.headline("ru"), "en": self.headline("en")},
            "reasons": [reason.to_dict() for reason in self.reasons],
        }


def _rank(cls: TemplateUpdateClass) -> int:
    return {_PATCH: 0, _MINOR: 1, _MAJOR: 2}[cls]


# ── снимок каталога версии ──


@dataclass(frozen=True)
class VersionSnapshot:
    """Разобранный каталог версии: манифест, документы по ростеру, файлы проверок и байты прочих файлов."""

    version_id: str | None
    manifest: dict[str, Any]
    roster: tuple[str, ...]
    documents: dict[str, Any]
    checks: dict[str, Any]
    files: dict[str, bytes]

    @property
    def langs(self) -> tuple[str, ...]:
        raw = self.manifest.get("langs")
        return tuple(str(code).lower() for code in raw) if isinstance(raw, list) else ()


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: не читается ({exc})") from exc


def _iter_files(version_dir: Path) -> Iterable[tuple[str, Path]]:
    for path in sorted(version_dir.rglob("*")):
        if not path.is_file() or path.name in _JUNK_NAMES:
            continue
        rel = path.relative_to(version_dir)
        if any(part in _JUNK_DIRS for part in rel.parts):
            continue
        yield rel.as_posix(), path


def _is_structured(rel: str) -> bool:
    """Файл, который сравнивается по разобранной модели, а не по байтам."""
    parts = rel.split("/")
    if rel == VERSION_MANIFEST:
        return True
    if len(parts) == 2 and parts[0] == "checks" and parts[1].endswith(".yaml"):  # noqa: PLR2004
        return True
    return len(parts) == 3 and parts[0] == "files" and parts[2] == DOC_MANIFEST  # noqa: PLR2004


def _content(data: bytes) -> bytes:
    return data if b"\x00" in data else data.replace(b"\r\n", b"\n")


def load_snapshot(version_dir: Path) -> VersionSnapshot:
    """Прочитать каталог версии. Битый YAML это `ValueError` с путём."""
    manifest = _read_yaml(version_dir / VERSION_MANIFEST) or {}
    if not isinstance(manifest, dict):
        raise TypeError(f"{version_dir / VERSION_MANIFEST}: манифест версии не словарь")
    roster: list[str] = []
    documents: dict[str, Any] = {}
    for entry in manifest.get("documents") or []:
        if isinstance(entry, str):
            doc_path = version_dir / "files" / entry / DOC_MANIFEST
            documents[entry] = (_read_yaml(doc_path) or {}) if doc_path.exists() else {}
            roster.append(entry)
        elif isinstance(entry, dict) and entry.get("id"):
            documents[str(entry["id"])] = entry
            roster.append(str(entry["id"]))
    checks_dir = version_dir / "checks"
    checks = {p.name: _read_yaml(p) or {} for p in sorted(checks_dir.glob("*.yaml"))} if checks_dir.is_dir() else {}
    files = {rel: _content(path.read_bytes()) for rel, path in _iter_files(version_dir) if not _is_structured(rel)}
    version_id = manifest.get("id")
    return VersionSnapshot(
        version_id=str(version_id) if version_id is not None else version_dir.name,
        manifest=manifest,
        roster=tuple(roster),
        documents=documents,
        checks=checks,
        files=files,
    )


# ── правила по путям ──


@dataclass(frozen=True)
class _Verdict:
    code: str
    minimum: TemplateUpdateClass
    suggested: TemplateUpdateClass
    hard: bool


_Judge = Callable[[Any, Any], "_Verdict | None"]

_SKIP = _Verdict("skip", _PATCH, _PATCH, hard=True)


def _hard(code: str, cls: TemplateUpdateClass, suggested: TemplateUpdateClass | None = None) -> _Verdict:
    return _Verdict(code, cls, suggested or cls, hard=True)


def _soft(code: str, suggested: TemplateUpdateClass) -> _Verdict:
    return _Verdict(code, _PATCH, suggested, hard=False)


_REMOVED = _hard("removed", _MINOR, _MAJOR)


@dataclass(frozen=True)
class _Rule:
    """Правило для узла по пути. `None` у события: спуститься глубже (для `changed`) или общий запасной разбор."""

    pattern: re.Pattern[str]
    added: _Verdict | _Judge | None = None
    removed: _Verdict | _Judge | None = None
    changed: _Verdict | _Judge | None = None


def _rule(pattern: str, *, added: Any = None, removed: Any = None, changed: Any = None) -> _Rule:
    return _Rule(re.compile(pattern), added=added, removed=removed, changed=changed)


def _whole(pattern: str, verdict: _Verdict | _Judge) -> _Rule:
    return _rule(pattern, added=verdict, removed=verdict, changed=verdict)


def _entity(pattern: str, added_code: str, removed: _Verdict = _REMOVED) -> _Rule:
    """Сущность списка или словаря: новая это minor, удалённая по `removed`, правка внутри разбирается глубже."""
    return _rule(pattern, added=_hard(added_code, _MINOR), removed=removed)


def _required_at(value: Any) -> int:
    try:
        return _REQUIRED_RANK[RequiredAt(str(value))]
    except ValueError:
        return _REQUIRED_RANK[RequiredAt.create]


def _judge_required_at(old: Any, new: Any) -> _Verdict:
    before = _required_at(RequiredAt.create.value if old is _MISSING else old)
    after = _required_at(RequiredAt.create.value if new is _MISSING else new)
    return _hard("required_stricter", _MINOR) if after > before else _hard("required_looser", _PATCH)


def _judge_required_flag(code: str) -> _Judge:
    def judge(old: Any, new: Any) -> _Verdict:
        became = new is not _MISSING and bool(new) and (old is _MISSING or not bool(old))
        return _hard(code, _MINOR) if became else _hard("required_looser", _PATCH)

    return judge


def _judge_field_added(_old: Any, new: Any) -> _Verdict:
    """Новое поле: необязательное без `default` и `auto` это исключение patch (мягкое), иначе minor."""
    if (
        isinstance(new, dict)
        and _required_at(new.get("required_at", RequiredAt.create.value)) == _REQUIRED_RANK[RequiredAt.never]
        and new.get("default") is None
        and new.get("auto") is None
    ):
        return _soft("optional_field_added", _PATCH)
    return _hard("field_added", _MINOR)


_ID = r"\[[^\]]+\]"
_KEY = r"[^.\[]+"
_PRESET = _hard("signing_preset", _PATCH)
_TUNING = _soft("check_tuning", _PATCH)

_RULES: tuple[_Rule, ...] = (
    # служебное и заметки: не влияют
    _whole(r"id|released_at|status|release|summary|changes|breaking_changes", _SKIP),
    # окружение и охват версии
    _whole(
        r"engine|latex_packages|dynamic_includes|requirements|nda|manifest_format|min_studio",
        _hard("build_setup", _MINOR),
    ),
    _whole(r"langs|supported_kinds|supported_staffing", _hard("version_scope", _MINOR)),
    _whole(r"checks_version", _TUNING),
    # поля и группы
    _entity(rf"meta_groups{_ID}", "group_added"),
    _rule(rf"meta_fields\.{_KEY}", added=_judge_field_added, removed=_REMOVED),
    _whole(rf"meta_fields\.{_KEY}\.required_at", _judge_required_at),
    _whole(rf"meta_fields\.{_KEY}\.type", _hard("field_type", _MINOR)),
    _whole(rf"meta_fields\.{_KEY}\.(?:default|auto|options)", _soft("field_default", _MINOR)),
    _whole(rf"meta_fields\.{_KEY}\.group", _hard("grouping", _PATCH)),
    _whole(rf"meta_fields\.{_KEY}\.supported_kinds", _hard("version_scope", _MINOR)),
    # анкеты
    _entity(rf"forms{_ID}", "form_added"),
    # подписи
    _whole(r"signatures\.(?:route|anchor_macros)", _PRESET),
    _entity(rf"signatures\.slots{_ID}", "slot_added"),
    _whole(rf"signatures\.slots{_ID}\.(?:placements|default_dates)", _PRESET),
    _whole(rf"signatures\.slots{_ID}\.default_placement", _soft("default_placement", _MINOR)),
    _whole(rf"signatures\.slots{_ID}\.required", _judge_required_flag("slot_required")),
    _whole(rf"signatures\.slots{_ID}\.(?:applies_to|per_author)", _hard("slot_scope", _MINOR)),
    # профили сдачи и пункты точек
    _entity(rf"pack_submission\.profiles{_ID}", "profile_added"),
    _whole(rf"pack_submission\.profiles{_ID}\.(?:signing_slots|signing_route)", _PRESET),
    _whole(rf"pack_submission\.profiles{_ID}\.deadline_hint", _hard("deadline_hint", _PATCH)),
    _whole(rf"pack_submission\.profiles{_ID}\.extra_items", _hard("extra_items", _MINOR)),
    _entity(rf"pack_submission\.profiles{_ID}\.items{_ID}", "item_added", removed=_hard("item_removed", _MINOR)),
    _whole(rf"pack_submission\.profiles{_ID}\.items{_ID}\.methods", _soft("methods", _MINOR)),
    _whole(rf"pack_submission\.profiles{_ID}\.items{_ID}\.signatures", _hard("item_signatures", _MINOR)),
    # документы: манифесты doc.yaml
    _whole(rf"documents{_ID}\.(?:source_file|output_file)", _soft("document_source", _PATCH)),
    _whole(rf"documents{_ID}\.group", _hard("grouping", _PATCH)),
    _whole(rf"documents{_ID}\.required", _judge_required_flag("required_stricter")),
    _whole(
        rf"documents{_ID}\.(?:supported_langs|supported_kinds|supported_staffing|scope|gost_ref)",
        _hard("document_scope", _MINOR),
    ),
    _whole(rf"documents{_ID}\.checks", _TUNING),
    _entity(rf"documents{_ID}\.variants", "variant_added"),
    _entity(rf"documents{_ID}\.variants{_ID}", "variant_added"),
    _whole(rf"documents{_ID}\.variants{_ID}\.(?:source_file|output_file)", _soft("document_source", _PATCH)),
    # проверки (checks/*.yaml)
    _rule(rf"checks{_ID}", added=_hard("check_file_added", _MINOR), removed=_soft("check_file_removed", _PATCH)),
    _whole(rf"checks{_ID}\.(?:label|ref|source)", _hard("text", _PATCH)),
    _rule(
        rf"checks{_ID}\.rules{_ID}",
        added=_hard("check_rule_added", _MINOR),
        removed=_soft("check_rule_removed", _PATCH),
    ),
    _whole(rf"checks{_ID}\.rules{_ID}\.(?:default_severity|severity|params)", _TUNING),
)


def _find_rule(path: str) -> _Rule | None:
    return next((rule for rule in _RULES if rule.pattern.fullmatch(path)), None)


# ── обход ──


class _Missing:
    def __repr__(self) -> str:
        return "<missing>"


_MISSING: Any = _Missing()


def _render(segments: tuple[str, ...]) -> str:
    out = ""
    for seg in segments:
        out += seg if seg.startswith("[") or not out else f".{seg}"
    return out


def _list_key(items: list[Any]) -> str | None:
    """Поле id элементов списка словарей (`id`, иначе `doc_id`); None, если список не такой."""
    for key in ("id", "doc_id"):
        ids = [item.get(key) for item in items if isinstance(item, dict)]
        if len(ids) == len(items) and all(ids) and len({str(i) for i in ids}) == len(ids):
            return key
    return None


def _keyed(old: list[Any], new: list[Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Списки словарей с id по ключу; None, если сравнивать их можно только целиком."""
    keys = {_list_key(items) for items in (old, new) if items}
    if len(keys) != 1:
        return None
    key = keys.pop()
    if key is None:
        return None
    return {str(i[key]): i for i in old}, {str(i[key]): i for i in new}


def _event(old: Any, new: Any) -> ChangeKind:
    if old is _MISSING:
        return "added"
    return "removed" if new is _MISSING else "changed"


class _Differ:
    def __init__(self) -> None:
        self.reasons: list[ChangeReason] = []

    def add(self, verdict: _Verdict, segments: tuple[str, ...], change: ChangeKind) -> None:
        if verdict is _SKIP:
            return
        self.reasons.append(
            ChangeReason(
                code=verdict.code,
                path=_render(segments),
                change=change,
                minimum=verdict.minimum,
                suggested=verdict.suggested,
                hard=verdict.hard,
            )
        )

    def walk(self, segments: tuple[str, ...], old: Any, new: Any) -> None:
        if old == new:
            return
        change = _event(old, new)
        rule = _find_rule(_render(segments))
        outcome = getattr(rule, change) if rule is not None else None
        if outcome is not None:
            verdict = outcome if isinstance(outcome, _Verdict) else outcome(old, new)
            if verdict is not None:
                self.add(verdict, segments, change)
                return
        if change == "changed" and not _is_text_map(segments, old, new) and self._descend(segments, old, new):
            return
        self.add(_fallback(segments), segments, change)

    def _descend(self, segments: tuple[str, ...], old: Any, new: Any) -> bool:
        if isinstance(old, dict) and isinstance(new, dict):
            for key in dict.fromkeys([*old, *new]):
                self.walk((*segments, str(key)), old.get(key, _MISSING), new.get(key, _MISSING))
            return True
        if isinstance(old, list) and isinstance(new, list):
            keyed = _keyed(old, new)
            if keyed is None:
                return False
            before, after = keyed
            common_before = [k for k in before if k in after]
            common_after = [k for k in after if k in before]
            if common_before != common_after:
                self.add(_hard("order", _PATCH), segments, "reordered")
            for key in dict.fromkeys([*before, *after]):
                self.walk((*segments, f"[{key}]"), before.get(key, _MISSING), after.get(key, _MISSING))
            return True
        return False


def _is_text_map(segments: tuple[str, ...], old: Any, new: Any) -> bool:
    """Текст по языкам (`help: {ru, en}`): одна причина на текст, а не по строке на язык."""
    if not segments or segments[-1] not in _TEXT_KEYS:
        return False
    return all(isinstance(v, dict) and all(_LOCALE_RE.match(str(k)) for k in v) for v in (old, new))


def _fallback(segments: tuple[str, ...]) -> _Verdict:
    """Узел без правила: текст это patch, оформление это patch, остальное minor (в строгую сторону)."""
    keys = [seg for seg in segments if not seg.startswith("[")]
    last = keys[-1] if keys else ""
    if last in _TEXT_KEYS or (len(keys) > 1 and _LOCALE_RE.match(last) and keys[-2] in _TEXT_KEYS):
        return _hard("text", _PATCH)
    if last in _PRESENTATION_KEYS:
        return _hard("presentation", _PATCH)
    return _hard("unclassified", _MINOR)


# ── файлы ──


def _bare(rel: str, langs: tuple[str, ...]) -> str:
    """`report/report.ru.tex` > `report/report.tex` по объявленным языкам версии."""
    head, _, name = rel.rpartition("/")
    parts = name.split(".")
    if len(parts) >= 3 and parts[-2].lower() in langs:  # noqa: PLR2004
        name = ".".join([*parts[:-2], parts[-1]])
    return f"{head}/{name}" if head else name


def _document_sources(snapshot: VersionSnapshot) -> set[str]:
    sources: set[str] = set()
    for doc in snapshot.documents.values():
        if not isinstance(doc, dict):
            continue
        entries = [doc, *[v for v in doc.get("variants") or [] if isinstance(v, dict)]]
        sources.update(str(e["source_file"]) for e in entries if e.get("source_file"))
    return sources


def _doc_dir(rel: str) -> str | None:
    parts = rel.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "files" else None  # noqa: PLR2004


def _diff_files(differ: _Differ, base: VersionSnapshot, new: VersionSnapshot) -> None:
    added_docs = set(new.roster) - set(base.roster)
    removed_docs = set(base.roster) - set(new.roster)
    sources = _document_sources(new)
    for rel in sorted(set(base.files) | set(new.files)):
        segments = (rel,)
        if rel in base.files and rel in new.files:
            if base.files[rel] != new.files[rel]:
                differ.add(_soft("file_changed", _PATCH), segments, "changed")
        elif rel in new.files:
            if _doc_dir(rel) in added_docs:
                continue
            is_source = rel.startswith("files/") and _bare(rel.removeprefix("files/"), new.langs) in sources
            verdict = _hard("document_file_added", _MINOR) if is_source else _soft("file_added", _PATCH)
            differ.add(verdict, segments, "added")
        elif _doc_dir(rel) not in removed_docs:
            differ.add(_soft("file_removed", _MINOR), segments, "removed")


def _diff_roster(differ: _Differ, base: VersionSnapshot, new: VersionSnapshot) -> None:
    for doc_id in new.roster:
        if doc_id not in base.roster:
            differ.add(_hard("document_added", _MINOR), ("documents", f"[{doc_id}]"), "added")
    for doc_id in base.roster:
        if doc_id not in new.roster:
            differ.add(_REMOVED, ("documents", f"[{doc_id}]"), "removed")
    common_before = [d for d in base.roster if d in new.roster]
    common_after = [d for d in new.roster if d in base.roster]
    if common_before != common_after:
        differ.add(_hard("order", _PATCH), ("documents",), "reordered")
    for doc_id in common_after:
        differ.walk(("documents", f"[{doc_id}]"), base.documents.get(doc_id), new.documents.get(doc_id))


def _without_documents(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "documents"}


def classify_snapshots(base: VersionSnapshot, new: VersionSnapshot) -> ChangeReport:
    """Класс изменения между двумя разобранными версиями (чистая функция)."""
    differ = _Differ()
    differ.walk((), _without_documents(base.manifest), _without_documents(new.manifest))
    _diff_roster(differ, base, new)
    for name in dict.fromkeys([*base.checks, *new.checks]):
        differ.walk(("checks", f"[{name}]"), base.checks.get(name, _MISSING), new.checks.get(name, _MISSING))
    _diff_files(differ, base, new)
    return ChangeReport(base_version=base.version_id, new_version=new.version_id, reasons=tuple(differ.reasons))


def classify_change(base_dir: Path, new_dir: Path) -> ChangeReport:
    """Класс изменения каталога `new_dir` относительно `base_dir` (оба каталоги версий одного шаблона)."""
    return classify_snapshots(load_snapshot(base_dir), load_snapshot(new_dir))
