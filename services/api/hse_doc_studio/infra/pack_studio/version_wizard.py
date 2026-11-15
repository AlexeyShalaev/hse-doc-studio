"""Мастер «Новая версия» над папкой паков рабочего пространства (порт `IPackVersions`, срез T10).

Логика копии, номера и выпуска та же, что у `hse-doc-studio pack new-version|classify|freeze`
(`infra/pack_studio/versions.py`, `core/template_diff.py`): здесь только раскладка пространства, выпущенность по
реестру базовой ветки (D10) и перевод отказов в коды Студии шаблонов.

- Состояние версии: класс черновика по классификатору относительно версии, с которой его сверяет линтер
  (`class_base`, иначе предыдущая), номера по классам, заметки и их черновик из отчёта (7.4); у выпущенной версии
  только признак правки мимо Студии и номер для переноса правок (7.3).
- Номера, выпущенные в базе, заняты, даже если их каталога в рабочем дереве нет (кто-то выпустил раньше, 4.3).
- Правки `version.yaml` и `template.yaml` точечные (D11): остальной текст байт в байт.

Пути идут от папки паков `root`; каталоги пака и шаблона не могут быть символьными ссылками.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.release_notes import draft_notes
from hse_doc_studio.core.pack_studio.versions import (
    LANGS,
    BaseRegistry,
    CreatedVersion,
    MovedVersion,
    NewVersionOptions,
    ReasonView,
    ReleasedVersionView,
    TemplateRef,
    VersionChoice,
    VersionNotesInput,
    VersionState,
)
from hse_doc_studio.core.template_diff import ChangeReport, classify_snapshots, load_snapshot
from hse_doc_studio.core.template_versions import classify_update, is_softer, parse_version_key, stricter
from hse_doc_studio.infra.pack_studio.base_ref import BaseReleases
from hse_doc_studio.infra.pack_studio.layout import (
    TEMPLATE_MANIFEST,
    VERSION_MANIFEST,
    VERSIONS_DIR,
    PackPathError,
    template_versions,
)
from hse_doc_studio.infra.pack_studio.versions import (
    LintFailedError,
    PackVersionError,
    class_base_of,
    copy_version,
    create_version,
    free_number,
    previous_version,
    release_version,
    renumber_version,
    restore_registry,
)
from hse_doc_studio.infra.pack_studio.yaml_edits import YamlEditError, delete, set_value
from hse_doc_studio.infra.template.releases import ReleaseEntry, load_releases, parse_releases, version_digest

_CLASSES = tuple(TemplateUpdateClass)
_NOTE_MAX = 2_000
_ITEM_MAX = 1_000
_ITEMS_MAX = 50
_FINDINGS_MAX = 50


def _err(code: PackStudioErrorCode, **ctx: object) -> PackStudioError:
    return PackStudioError(code, None, **ctx)


class _RegistryBase(BaseReleases):
    """Реестр базы одного шаблона из уже прочитанного текста (git): запрет на замену выпущенной там записи."""

    def __init__(self, entries: Mapping[str, ReleaseEntry]) -> None:
        super().__init__("base")
        self._entries = dict(entries)

    def releases(self, template_dir: Path) -> dict[str, ReleaseEntry]:  # noqa: ARG002 — реестр одного шаблона
        return dict(self._entries)


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _manifest(version_dir: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(_read(version_dir / VERSION_MANIFEST))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _class(raw: Any) -> TemplateUpdateClass | None:
    try:
        return TemplateUpdateClass(str(raw)) if raw else None
    except ValueError:
        return None


def _notes(raw: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw, dict):
        return dict.fromkeys(LANGS, ())
    return {lang: tuple(str(i) for i in raw.get(lang) or [] if i is not None) for lang in LANGS}


def _latest(versions: Collection[str]) -> str | None:
    keyed = {v: k for v in versions if (k := parse_version_key(v)) is not None}
    return max(keyed, key=lambda v: keyed[v]) if keyed else None


def _base_entries(registry: BaseRegistry) -> dict[str, ReleaseEntry]:
    if registry.text is None:
        return {}
    try:
        return parse_releases(registry.text)
    except yaml.YAMLError:
        return {}


class PackVersionWizard:
    """Реализация `IPackVersions` (core/pack_studio/protocols.py) функциями CLI паков."""

    # ── чтение ───────────────────────────────────────────────────────────────

    def options(self, root: Path, template: TemplateRef, registry: BaseRegistry) -> NewVersionOptions:
        template_dir = self._template_dir(root, template)
        versions = template_versions(template_dir)
        local = load_releases(template_dir)
        choices = tuple(
            VersionChoice(
                version=v,
                status=_status(template_dir / VERSIONS_DIR / v),
                released=v in registry.versions,
                registered=v in local,
                modified=v in registry.versions and self._modified(template_dir / VERSIONS_DIR / v, registry, v),
            )
            for v in versions
        )
        released = [c.version for c in choices if c.released or c.registered]
        default_base = _latest(released) or _latest(versions)
        taken = [*versions, *registry.versions]
        latest = _latest(taken)
        numbers = {cls: free_number(latest, cls, taken) for cls in _CLASSES} if latest else {}
        return NewVersionOptions(
            template=template,
            versions=choices,
            default_base=default_base,
            numbers=numbers,
            default_version=_default_version(template_dir),
        )

    def state(self, root: Path, ref: VersionRef, registry: BaseRegistry) -> VersionState:
        template_dir = self._template_dir(root, TemplateRef(ref.pack, ref.template))
        version_dir = self._version_dir(template_dir, ref.version)
        manifest = _manifest(version_dir)
        released = ref.version in registry.versions
        modified = released and self._modified(version_dir, registry, ref.version)
        local = load_releases(template_dir).get(ref.version)
        registered = local is not None
        outdated = local is not None and not released and version_digest(version_dir) != local.digest
        raw_release = manifest.get("release")
        release: dict[str, Any] = raw_release if isinstance(raw_release, dict) else {}
        note = release.get("note") if isinstance(release.get("note"), str) else None
        common: dict[str, Any] = {
            "ref": ref,
            "status": _status(version_dir),
            "released": released,
            "modified": modified,
            "registered": registered,
            "declared": _class(release.get("kind")),
            "note": note,
            "changes": _notes(manifest.get("changes")),
            "breaking_changes": _notes(manifest.get("breaking_changes")),
            "is_default": _default_version(template_dir) == ref.version,
            "release_outdated": outdated,
        }
        if released:
            move_to = self._move_number(template_dir, ref.version, registry) if modified else None
            return _empty_state(common, move_to=move_to)
        base = class_base_of(version_dir)
        if base is None:
            return _empty_state(common, numbers=self._numbers(template_dir, ref.version, None, registry))
        try:
            base_snapshot = load_snapshot(template_dir / VERSIONS_DIR / base)
            new_snapshot = load_snapshot(version_dir)
        except (OSError, UnicodeDecodeError, TypeError, ValueError) as exc:
            return _empty_state(common, base=base, error=str(exc)[:500])
        report = classify_snapshots(base_snapshot, new_snapshot)
        drafts = draft_notes(report, new_snapshot, base_snapshot)
        by_number = classify_update(base, ref.version)
        return VersionState(
            **common,
            base=base,
            minimum=report.minimum,
            suggested=report.suggested,
            by_number=by_number,
            number_ok=_number_ok(report, by_number, common["declared"]),
            headline={lang: report.headline(lang) for lang in LANGS},
            reasons=tuple(_reason(r) for r in report.reasons),
            numbers=self._numbers(template_dir, ref.version, base, registry),
            draft_changes=drafts.changes,
            draft_breaking=drafts.breaking_changes,
        )

    # ── шаги мастера ─────────────────────────────────────────────────────────

    def create(  # noqa: PLR0913 — шаг 1 мастера
        self,
        root: Path,
        template: TemplateRef,
        *,
        base: str | None,
        to: str | None,
        update_class: TemplateUpdateClass | None,
        registry: BaseRegistry,
        today: date,
    ) -> CreatedVersion:
        template_dir = self._template_dir(root, template)
        versions = template_versions(template_dir)
        if base is not None and base not in versions:
            raise _err(PackStudioErrorCode.version_not_found, version=base)
        taken = list(registry.versions)
        if to is not None:
            self._check_free(template_dir, to, taken, update_class or TemplateUpdateClass.patch)
        if base is None:
            base = self.options(root, template, registry).default_base
        try:
            created = create_version(
                template_dir, base=base, to=to, update_class=update_class, today=today, taken=taken
            )
        except PackPathError as exc:
            raise _err(PackStudioErrorCode.version_not_found, reason=str(exc)) from None
        except PackVersionError as exc:
            raise _err(PackStudioErrorCode.version_number_invalid, reason=str(exc)) from None
        return CreatedVersion(
            ref=template.version(created.version),
            base=created.base,
            update_class=created.update_class,
            warnings=created.notes,
        )

    def save_notes(self, root: Path, ref: VersionRef, notes: VersionNotesInput) -> None:
        template_dir = self._template_dir(root, TemplateRef(ref.pack, ref.template))
        path = self._version_dir(template_dir, ref.version) / VERSION_MANIFEST
        text = _read(path)
        try:
            edited = _notes_text(text, notes)
        except (YamlEditError, yaml.YAMLError) as exc:
            raise _err(PackStudioErrorCode.yaml_patch_conflict, op=0, reason=str(exc)[:300]) from None
        if edited != text:
            path.write_bytes(edited.encode("utf-8"))

    def renumber(self, root: Path, ref: VersionRef, to: str, registry: BaseRegistry, today: date) -> MovedVersion:
        template_dir = self._template_dir(root, TemplateRef(ref.pack, ref.template))
        version_dir = self._version_dir(template_dir, ref.version)
        if to == ref.version:
            return MovedVersion(ref=ref, previous=ref.version)
        self._check_free(template_dir, to, list(registry.versions), TemplateUpdateClass.patch, own=ref.version)
        self._check_class(version_dir, to)
        try:
            moved = renumber_version(template_dir, ref.version, to, taken=list(registry.versions), today=today)
        except PackPathError as exc:
            raise _err(PackStudioErrorCode.version_not_found, reason=str(exc)) from None
        except PackVersionError as exc:
            raise _err(PackStudioErrorCode.version_number_invalid, reason=str(exc)) from None
        return MovedVersion(
            ref=VersionRef(ref.pack, ref.template, moved.version),
            previous=ref.version,
            unreleased=moved.unreleased,
            edited=moved.edited,
        )

    def move_edits(
        self, root: Path, ref: VersionRef, to: str | None, registry: BaseRegistry, today: date
    ) -> MovedVersion:
        """Копия изменённого выпущенного каталога в новый черновик и записи базы в реестре рабочего дерева (7.3).

        Свои заметки остаются, если реестр рабочего дерева не совпадает с базой по этой версии (номер выпущен в базе
        раньше, 4.3): это черновик автора. Правка мимо Студии поверх чужого выпуска получает пустые заметки.
        Каталог выпущенной версии возвращает к выпуску вызывающий (git): у папки вернуть его нечем.
        """
        template_dir = self._template_dir(root, TemplateRef(ref.pack, ref.template))
        version_dir = self._version_dir(template_dir, ref.version)
        if ref.version not in registry.versions or not self._modified(version_dir, registry, ref.version):
            raise _err(PackStudioErrorCode.version_not_modified)
        taken = [*template_versions(template_dir), *registry.versions]
        to = to or self._move_number(template_dir, ref.version, registry)
        self._check_free(template_dir, to, taken, TemplateUpdateClass.patch)
        local = load_releases(template_dir).get(ref.version)
        keep_notes = local is None or local.digest != registry.versions[ref.version]
        try:
            copy_version(template_dir, ref.version, to, keep_notes=keep_notes, today=today)
        except PackVersionError as exc:
            raise _err(PackStudioErrorCode.version_number_invalid, reason=str(exc)) from None
        edited: list[str] = []
        base_entries = _base_entries(registry)
        if base_entries and restore_registry(template_dir, base_entries):
            edited.append(str(template_dir / "releases.yaml"))
        return MovedVersion(ref=VersionRef(ref.pack, ref.template, to), previous=ref.version, edited=tuple(edited))

    def release(  # noqa: PLR0913 — шаг «Выпустить»
        self,
        root: Path,
        ref: VersionRef,
        *,
        kind: TemplateUpdateClass | None,
        set_default: bool,
        registry: BaseRegistry,
        today: date,
    ) -> ReleasedVersionView:
        template_dir = self._template_dir(root, TemplateRef(ref.pack, ref.template))
        version_dir = self._version_dir(template_dir, ref.version)
        self._check_release_class(version_dir, kind)
        replace = ref.version in load_releases(template_dir)
        base = _RegistryBase(_base_entries(registry)) if registry.from_git else None
        try:
            released = release_version(
                template_dir,
                ref.version,
                kind=kind,
                mark_released=True,
                set_default=set_default,
                replace=replace,
                base=base,
                today=today,
            )
        except LintFailedError as exc:
            raise _err(
                PackStudioErrorCode.lint_failed,
                errors=len(exc.errors),
                warnings=0,
                findings=[
                    {"severity": "error", "check": "lint", "path": ref.dir, "message": message}
                    for message in exc.errors[:_FINDINGS_MAX]
                ],
            ) from None
        except PackPathError as exc:
            raise _err(PackStudioErrorCode.version_not_found, reason=str(exc)) from None
        except PackVersionError as exc:
            raise _err(PackStudioErrorCode.version_number_invalid, reason=str(exc)) from None
        entry = released.entry
        return ReleasedVersionView(
            ref=ref,
            digest=entry.digest,
            kind=entry.kind,
            previous=released.previous,
            replaced=released.replaced,
            default_set=set_default,
            edited=tuple(_rel(root, p) for p in released.edited),
            warnings=released.warnings,
        )

    # ── служебное ────────────────────────────────────────────────────────────

    @staticmethod
    def _template_dir(root: Path, template: TemplateRef) -> Path:
        pack_dir = root / template.pack
        templates = pack_dir / "templates"
        template_dir = templates / template.template
        if any(p.is_symlink() for p in (pack_dir, templates, template_dir)):
            raise _err(PackStudioErrorCode.path_not_allowed)
        if not (template_dir / VERSIONS_DIR).is_dir() or (template_dir / VERSIONS_DIR).is_symlink():
            raise _err(PackStudioErrorCode.version_not_found)
        return template_dir

    @staticmethod
    def _version_dir(template_dir: Path, version: str) -> Path:
        version_dir = template_dir / VERSIONS_DIR / version
        if version_dir.is_symlink() or not (version_dir / VERSION_MANIFEST).is_file():
            raise _err(PackStudioErrorCode.version_not_found, version=version)
        return version_dir

    @staticmethod
    def _modified(version_dir: Path, registry: BaseRegistry, version: str) -> bool:
        if not version_dir.is_dir():
            return False
        return version_digest(version_dir) != registry.versions.get(version)

    @staticmethod
    def _move_number(template_dir: Path, version: str, registry: BaseRegistry) -> str:
        """Номер для переноса правок: тот же класс, что у номера версии, после последней известной."""
        previous = previous_version(template_dir, version)
        cls = (classify_update(previous, version) if previous else None) or TemplateUpdateClass.patch
        taken = [*template_versions(template_dir), *registry.versions]
        return free_number(_latest(taken) or version, cls, taken)

    @staticmethod
    def _numbers(
        template_dir: Path, version: str, base: str | None, registry: BaseRegistry
    ) -> dict[TemplateUpdateClass, str]:
        """Номер черновика по каждому классу: свой, если его класс такой и есть, иначе свободный следующий."""
        others = [v for v in template_versions(template_dir) if v != version]
        taken = [*others, *(v for v in registry.versions if v != version)]
        latest = _latest(taken)
        numbers: dict[TemplateUpdateClass, str] = {}
        own = classify_update(base, version) if base else None
        for cls in _CLASSES:
            if own is cls:
                numbers[cls] = version
            elif latest is not None:
                numbers[cls] = free_number(latest, cls, taken)
        return numbers

    @staticmethod
    def _check_free(
        template_dir: Path,
        to: str,
        taken: Collection[str],
        update_class: TemplateUpdateClass,
        *,
        own: str | None = None,
    ) -> None:
        key = parse_version_key(to)
        if key is None or "/" in to or to.startswith("."):
            raise _err(PackStudioErrorCode.version_number_invalid, version=to, reason="format")
        everything = [v for v in [*template_versions(template_dir), *taken] if v != own]
        keys = {parse_version_key(v) for v in everything}
        if key in keys or (template_dir / VERSIONS_DIR / to).exists():
            latest = _latest(everything) or to
            raise _err(
                PackStudioErrorCode.version_taken,
                version=to,
                suggested=free_number(latest, update_class, everything),
            )

    @staticmethod
    def _check_class(version_dir: Path, to: str) -> None:
        """Новый номер не мягче минимума по жёстким правилам (7.1, шаг 3)."""
        base = class_base_of(version_dir)
        if base is None:
            return
        by_number = classify_update(base, to)
        if by_number is None:
            raise _err(PackStudioErrorCode.version_number_invalid, version=to, reason="not_higher", base=base)
        report = _report(version_dir.parent / base, version_dir)
        if report is not None and is_softer(by_number, report.minimum):
            raise _err(
                PackStudioErrorCode.class_softer_than_changes,
                minimum=report.minimum.value,
                chosen=by_number.value,
            )

    @staticmethod
    def _check_release_class(version_dir: Path, kind: TemplateUpdateClass | None) -> None:
        base = class_base_of(version_dir)
        if base is None:
            return
        report = _report(version_dir.parent / base, version_dir)
        if report is None:
            return
        by_number = classify_update(base, version_dir.name)
        declared = kind or _class((_manifest(version_dir).get("release") or {}).get("kind"))
        effective = stricter(by_number, declared) or by_number
        if effective is not None and is_softer(effective, report.minimum):
            raise _err(
                PackStudioErrorCode.class_softer_than_changes,
                minimum=report.minimum.value,
                chosen=effective.value,
            )


def _report(base_dir: Path, new_dir: Path) -> ChangeReport | None:
    try:
        return classify_snapshots(load_snapshot(base_dir), load_snapshot(new_dir))
    except (OSError, UnicodeDecodeError, TypeError, ValueError):
        return None


def _status(version_dir: Path) -> str | None:
    raw = _manifest(version_dir).get("status")
    return str(raw) if raw is not None else None


def _default_version(template_dir: Path) -> str | None:
    try:
        data = yaml.safe_load(_read(template_dir / TEMPLATE_MANIFEST))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    raw = data.get("default_version") if isinstance(data, dict) else None
    return str(raw) if raw is not None else None


def _number_ok(
    report: ChangeReport, by_number: TemplateUpdateClass | None, declared: TemplateUpdateClass | None
) -> bool:
    if by_number is not None and is_softer(by_number, report.minimum):
        return False
    effective = stricter(by_number, report.minimum) or report.minimum
    return declared is None or not is_softer(declared, effective)


def _reason(reason: Any) -> ReasonView:
    return ReasonView(
        code=reason.code,
        path=reason.path,
        change=reason.change,
        minimum=reason.minimum,
        suggested=reason.suggested,
        hard=reason.hard,
        exception=reason.exception,
        message={lang: reason.message(lang) for lang in LANGS},
    )


def _empty_state(common: dict[str, Any], **extra: Any) -> VersionState:
    fields: dict[str, Any] = {
        "base": None,
        "minimum": None,
        "suggested": None,
        "by_number": None,
        "number_ok": True,
        "headline": {},
        "reasons": (),
        "numbers": {},
        "draft_changes": dict.fromkeys(LANGS, ()),
        "draft_breaking": dict.fromkeys(LANGS, ()),
    }
    fields.update(extra)
    return VersionState(**common, **fields)


def _clean(items: tuple[str, ...]) -> list[str]:
    return [item.strip()[:_ITEM_MAX] for item in items if item.strip()][:_ITEMS_MAX]


def _notes_text(text: str, notes: VersionNotesInput) -> str:
    """Заметки и объяснение класса точечными правками: списки блоком, как в паках; остальной текст байт в байт."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise YamlEditError(f"{VERSION_MANIFEST} не словарь")
    for block, value in (("changes", notes.changes), ("breaking_changes", notes.breaking_changes)):
        if value is not None:
            text = _lists_text(text, block, data.get(block), value)
    if notes.note is not None:
        text = _note_text(text, data.get("release"), notes.note.strip()[:_NOTE_MAX])
    return text


def _lists_text(text: str, block: str, current: Any, value: Mapping[str, tuple[str, ...]]) -> str:
    lists = {lang: _clean(tuple(value.get(lang, ()))) for lang in LANGS}
    if isinstance(current, dict):
        for lang in LANGS:
            text = set_value(text, (block, lang), lists[lang], block=True)
        return text
    if any(lists.values()):
        return set_value(text, (block,), lists, block=True)
    return text


def _note_text(text: str, release: Any, note: str) -> str:
    """`release.note`: объяснение класса для мягких правил (7.2); пустое убирает ключ, пустой `release` уходит."""
    if not isinstance(release, dict):
        return set_value(text, ("release",), {"note": note}, after="status") if note else text
    if note:
        return set_value(text, ("release", "note"), note)
    if "note" not in release:
        return text
    if set(release) == {"note"}:
        return delete(text, ("release",))
    return delete(text, ("release", "note"))


def _rel(root: Path, raw: str) -> str:
    try:
        return Path(raw).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return raw
