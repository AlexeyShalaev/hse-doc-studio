"""Новая версия шаблона и её выпуск из командной строки (template-studio.md, 7.1, 7.3 и 11).

* `create_version`: шаг 1 мастера. Каталог базы (по умолчанию последней версии) копируется в `versions/<номер>/`,
  номер считается по классу (`patch`, `minor`, `major`) от последней версии шаблона или задаётся явно. В копии
  `version.yaml` правится точечно (`yaml_edits`), остальные байты те же: `id`, `status: beta`, `released_at`
  сегодня, блок `release` убран (класс и объяснение пишет автор), заметки `changes` и `breaking_changes` пусты.
* `release_version`: шаг 5 мастера и `releases freeze`. По желанию отмечает версию выпущенной (`status: stable`,
  `released_at`, `release.kind`) и ставит её `default_version` шаблона, затем гоняет линтер и схемы и вносит версию в
  `releases.yaml`. Запись уже внесённой версии заменяется только с `replace`, и только пока версия не выпущена
  в базе (7.1: правка после «Выпустить», пока PR не слит).

Выпущенная версия при этом только база для копии (7.3): ни одна операция не пишет в её каталог.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.template_versions import classify_update, is_softer, parse_version_key
from hse_doc_studio.infra.pack_studio.base_ref import BaseReleases
from hse_doc_studio.infra.pack_studio.check import check_version
from hse_doc_studio.infra.pack_studio.layout import (
    TEMPLATE_MANIFEST,
    VERSION_MANIFEST,
    VERSIONS_DIR,
    PackPathError,
    require_template,
    template_versions,
)
from hse_doc_studio.infra.pack_studio.yaml_edits import YamlEditError, delete, set_value
from hse_doc_studio.infra.template.releases import ReleaseEntry, freeze, load_releases

_JUNK = ("__pycache__", ".DS_Store", "Thumbs.db", "desktop.ini")


class PackVersionError(ValueError):
    """Версию нельзя создать или выпустить: номер занят, не выше базы, мягче класса, версия уже выпущена."""


def next_number(latest: str, update_class: TemplateUpdateClass) -> str:
    """Следующий номер после `latest`: patch `2026.1.3` > `2026.1.4`, minor > `2026.2.0`, major > `2027.1`."""
    key = parse_version_key(latest)
    if key is None:
        raise PackVersionError(f"номер {latest} не разобран (нужен ГОД.MINOR.PATCH)")
    year, minor, patch = key
    if update_class is TemplateUpdateClass.major:
        return f"{year + 1}.1"
    if update_class is TemplateUpdateClass.minor:
        return f"{year}.{minor + 1}.0"
    return f"{year}.{minor}.{patch + 1}"


@dataclass(frozen=True)
class NewVersion:
    template_dir: Path
    base: str
    version: str
    update_class: TemplateUpdateClass | None
    path: Path
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template_dir.name,
            "base": self.base,
            "version": self.version,
            "class": self.update_class.value if self.update_class else None,
            "path": str(self.path),
            "notes": list(self.notes),
        }


def _empty_notes(text: str, data: dict[str, Any]) -> str:
    """Заметки базы к черновику не относятся: списки `changes` и `breaking_changes` пусты, ключи и комментарии те же."""
    for block in ("changes", "breaking_changes"):
        notes = data.get(block)
        for lang, items in notes.items() if isinstance(notes, dict) else ():
            if items:
                text = set_value(text, (block, lang), [])
    return text


def _draft_manifest(text: str, version: str, today: date) -> str:
    """`version.yaml` черновика: точечные правки копии базы, остальной текст байт в байт."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise PackVersionError(f"{VERSION_MANIFEST} базы не словарь")
    text = set_value(text, ("id",), version)
    text = set_value(text, ("status",), "beta", after="id")
    if "released_at" in data:
        text = set_value(text, ("released_at",), today)
    if "release" in data:
        text = delete(text, ("release",))
    return _empty_notes(text, data)


def _plan_number(
    template_dir: Path, base: str | None, to: str | None, update_class: TemplateUpdateClass | None
) -> tuple[str, str, TemplateUpdateClass, list[str]]:
    """База, номер, класс по номеру и замечания для новой версии; номер свободен и выше базы."""
    versions = template_versions(template_dir)
    if not versions:
        raise PackPathError(f"{template_dir}: в versions/ нет версий для копии")
    latest = next(reversed(versions))
    base = base or latest
    if base not in versions:
        raise PackPathError(f"{template_dir.name}: версии {base} нет в versions/")
    to = to or next_number(latest, update_class or TemplateUpdateClass.patch)
    to_key = parse_version_key(to)
    if to_key is None:
        raise PackVersionError(f"номер {to} не разобран (нужен ГОД.MINOR.PATCH)")
    if (template_dir / VERSIONS_DIR / to).exists() or to_key in versions.values():
        raise PackVersionError(f"{template_dir.name}@{to}: такая версия уже есть")
    by_number = classify_update(base, to)
    if by_number is None:
        raise PackVersionError(f"{template_dir.name}: номер {to} должен быть выше базы {base}")
    notes = [f"номер {to} ниже последней версии {latest}"] if to_key < versions[latest] else []
    unreleased = [v for v in versions if v not in load_releases(template_dir)]
    if unreleased:
        notes.append("уже есть невыпущенные версии: " + ", ".join(unreleased))
    return base, to, by_number, notes


def create_version(
    template_dir: Path,
    *,
    base: str | None = None,
    to: str | None = None,
    update_class: TemplateUpdateClass | None = None,
    today: date | None = None,
) -> NewVersion:
    """Копия версии `base` (по умолчанию последней) в новый номер: `to` или следующий по `update_class` (patch).

    Копия собирается во временном каталоге рядом и переименовывается целиком: при ошибке новой версии нет.
    """
    require_template(template_dir)
    base, to, by_number, notes = _plan_number(template_dir, base, to, update_class)
    target = template_dir / VERSIONS_DIR / to
    staging = Path(tempfile.mkdtemp(prefix=f".{to}.", dir=template_dir / VERSIONS_DIR))
    try:
        copy = staging / "v"
        shutil.copytree(template_dir / VERSIONS_DIR / base, copy, symlinks=True, ignore=shutil.ignore_patterns(*_JUNK))
        manifest = copy / VERSION_MANIFEST
        draft = _draft_manifest(_read(manifest), to, today or date.today())  # noqa: DTZ011 — местный календарь автора
        manifest.write_bytes(draft.encode("utf-8"))
        copy.rename(target)
    except (OSError, YamlEditError, yaml.YAMLError) as exc:
        raise PackVersionError(f"{template_dir.name}@{to}: копия не создана ({exc})") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return NewVersion(template_dir, base, to, by_number, target, tuple(notes))


@dataclass(frozen=True)
class Released:
    template_dir: Path
    entry: ReleaseEntry
    previous: str | None
    replaced: bool
    edited: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template_dir.name,
            "version": self.entry.version,
            "digest": self.entry.digest,
            "kind": self.entry.kind.value if self.entry.kind else None,
            "previous": self.previous,
            "replaced": self.replaced,
            "edited": list(self.edited),
            "warnings": list(self.warnings),
        }


class LintFailedError(PackVersionError):
    """Линтер или схема нашли ошибки в выпускаемой версии; правки отменены."""

    def __init__(self, message: str, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = errors


def _read(path: Path) -> str:
    """Текст файла как есть, без перевода строк: правка и откат не меняют посторонних байтов."""
    return path.read_bytes().decode("utf-8")


class _Edits:
    """Правки файлов выпуска с откатом: отказ на любом шаге возвращает файлы как были."""

    def __init__(self) -> None:
        self._saved: dict[Path, str] = {}
        self.edited: list[str] = []

    def write(self, path: Path, text: str) -> None:
        original = self._saved.setdefault(path, _read(path))
        if text != original:
            path.write_bytes(text.encode("utf-8"))
            self.edited.append(str(path))

    def rollback(self) -> None:
        for path, text in self._saved.items():
            path.write_bytes(text.encode("utf-8"))


def _previous_release(entries: dict[str, ReleaseEntry], version: str) -> str | None:
    key = parse_version_key(version)
    earlier = {v: k for v in entries if (k := parse_version_key(v)) is not None and key is not None and k < key}
    return max(earlier, key=lambda v: earlier[v]) if earlier else None


def _allow_freeze(
    template_dir: Path, version: str, entries: dict[str, ReleaseEntry], *, replace: bool, base: BaseReleases | None
) -> None:
    """Запись внесённой версии заменяется только с `replace`, только пока версия не выпущена в базе (7.1, 7.3)."""
    if version not in entries:
        return
    if not replace:
        raise PackVersionError(
            f"{template_dir.name}@{version}: версия уже внесена в releases.yaml; --replace пересчитает "
            f"дайджест, пока выпуск не слит в базовую ветку"
        )
    if base is not None:
        if version in base.releases(template_dir):
            raise PackVersionError(
                f"{template_dir.name}@{version}: версия выпущена в {base.ref}, её каталог и запись неизменны"
            )
        return
    newest = max(entries, key=lambda v: parse_version_key(v) or (0, 0, 0))
    if version != newest:
        raise PackVersionError(
            f"{template_dir.name}@{version}: заменить можно только последнюю внесённую версию ({newest}); "
            f"передайте --base, чтобы сверить с базовой веткой"
        )


def _release_kind(
    template_dir: Path, version: str, entries: dict[str, ReleaseEntry], manifest: Any, kind: TemplateUpdateClass | None
) -> tuple[str | None, TemplateUpdateClass]:
    """Предыдущая выпущенная и класс выпуска: `kind`, `release.kind` или по номеру; мягче номера нельзя."""
    previous = _previous_release({v: e for v, e in entries.items() if v != version}, version)
    by_number = classify_update(previous, version) if previous else TemplateUpdateClass.major
    release = manifest.get("release") if isinstance(manifest, dict) else None
    raw = release.get("kind") if isinstance(release, dict) else None
    declared = TemplateUpdateClass(raw) if raw in {c.value for c in TemplateUpdateClass} else None
    effective = kind or declared or by_number or TemplateUpdateClass.major
    if by_number is not None and is_softer(effective, by_number):
        raise PackVersionError(
            f"{template_dir.name}@{version}: класс {effective.value} мягче номера ({by_number.value} после "
            f"{previous}); строже можно, мягче нельзя"
        )
    return previous, effective


def _released_manifest(text: str, manifest: Any, kind: TemplateUpdateClass, today: date) -> str:
    """`status: stable`, `released_at` и `release.kind` точечными правками (шаг «Выпустить», 7.1)."""
    text = set_value(text, ("status",), "stable", after="id")
    text = set_value(text, ("released_at",), today, after="id")
    release = manifest.get("release") if isinstance(manifest, dict) else None
    if isinstance(release, dict):
        return set_value(text, ("release", "kind"), kind.value)
    return set_value(text, ("release",), {"kind": kind.value}, after="status")


def _release_paths(template_dir: Path, version: str, *, set_default: bool) -> tuple[Path, Path, Path]:
    require_template(template_dir)
    version_dir = template_dir / VERSIONS_DIR / version
    manifest_path = version_dir / VERSION_MANIFEST
    if not manifest_path.is_file():
        raise PackPathError(f"{template_dir.name}: версии {version} нет (нет {manifest_path})")
    template_path = template_dir / TEMPLATE_MANIFEST
    if set_default and not template_path.is_file():
        raise PackPathError(f"{template_dir}: нет {TEMPLATE_MANIFEST}")
    return version_dir, manifest_path, template_path


def release_version(  # noqa: PLR0913 — шаги выпуска включаются по отдельности
    template_dir: Path,
    version: str,
    *,
    kind: TemplateUpdateClass | None = None,
    mark_released: bool = False,
    set_default: bool = False,
    replace: bool = False,
    base: BaseReleases | None = None,
    today: date | None = None,
) -> Released:
    """Выпуск версии: правки `version.yaml` и `template.yaml` (по флагам), линтер и схемы, запись в `releases.yaml`.

    Класс в реестр: `kind`, иначе `release.kind` манифеста, иначе по номеру относительно предыдущей выпущенной
    (первая версия шаблона это major). Мягче класса по номеру нельзя. Любой отказ отменяет все правки.
    """
    version_dir, manifest_path, template_path = _release_paths(template_dir, version, set_default=set_default)
    entries = load_releases(template_dir)
    _allow_freeze(template_dir, version, entries, replace=replace, base=base)
    manifest = yaml.safe_load(_read(manifest_path)) or {}
    previous, effective = _release_kind(template_dir, version, entries, manifest, kind)

    edits = _Edits()
    try:
        if mark_released:
            today = today or date.today()  # noqa: DTZ011 — дата выпуска по местному календарю автора
            edits.write(manifest_path, _released_manifest(_read(manifest_path), manifest, effective, today))
        if set_default:
            edits.write(template_path, set_value(_read(template_path), ("default_version",), version))
        checked = check_version(version_dir)
        errors = [f.message for f in checked.findings if f.severity == "error"]
        if errors:
            raise LintFailedError(f"{template_dir.name}@{version}: проверки нашли ошибки, версия не выпущена", errors)
        entry = freeze(template_dir, version, effective, replace=replace)
    except PackVersionError:
        edits.rollback()
        raise
    except ValueError as exc:  # YamlEditError и отказ releases.freeze (не stable)
        edits.rollback()
        hint = "" if mark_released else " (--release отметит её выпущенной: status: stable, released_at, release.kind)"
        raise PackVersionError(f"{template_dir.name}@{version}: {exc}{hint}") from exc
    warnings = tuple(f.message for f in checked.findings if f.severity == "warning")
    return Released(template_dir, entry, previous, version in entries, tuple(edits.edited), warnings)
