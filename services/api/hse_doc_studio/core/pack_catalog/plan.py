"""План «Применить» по разбору ревизии источника (docs/design/template-studio.md, 10.3 и 10.4). Чистая функция.

Что появится в каталоге: только выпущенные версии (есть в `releases.yaml` источника), каталог которых совпал с
дайджестом реестра, понятные этой Студии и без ошибок линтера. Отказ всего применения:

- пак с id вшитого пака без галочки «Заменить встроенный» или пак, который уже несёт другой источник;
- версия с тем же номером, что уже есть в каталоге, но с другим дайджестом («версия изменена в источнике»):
  проекты закрепили дайджест в `project.lock`, подменять каталог нельзя;
- новая версия с ошибками линтера или с каталогом, изменённым после выпуска.

Версии новее этой Студии (`min_studio`, `manifest_format`) пропускаются с пометкой «не для этой Студии», это не
отказ: они появятся после обновления Студии.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.catalog import PackOrigin, PackOriginKind
from hse_doc_studio.core.pack_catalog.entities import InspectedPack, InspectedTree, InspectedVersion
from hse_doc_studio.core.pack_catalog.store import is_store_name
from hse_doc_studio.core.template_versions import MANIFEST_FORMAT, parse_version_key, studio_satisfies


class Verdict(StrEnum):
    # Появится в каталоге.
    new = "new"
    # Уже в каталоге с тем же дайджестом.
    present = "present"
    # Тот же номер уже в каталоге с другим дайджестом: отказ.
    changed = "changed"
    # Новее этой Студии: пропускается.
    incompatible = "incompatible"
    # Каталог не совпал с реестром выпусков, ошибки линтера или лоадер её не понял: отказ, если версия новая.
    invalid = "invalid"
    # Нет в `releases.yaml` источника: в каталог не попадает.
    unreleased = "unreleased"


class PackConflict(StrEnum):
    # Пак с id вшитого пака, галочки «Заменить встроенный» нет.
    builtin = "builtin"
    # Пак уже несёт другой источник каталога.
    other_source = "other_source"
    # Id пака не годится в путь хранилища или `pack.yaml` не разобран.
    invalid = "invalid"


class Blocker(StrEnum):
    pack_conflict = "pack_conflict"
    version_changed = "version_changed"
    version_invalid = "version_invalid"
    no_packs = "no_packs"


@dataclass(frozen=True)
class PlannedVersion:
    template: str
    version: str
    verdict: Verdict
    digest: str | None
    kind: str | None = None
    min_studio: str | None = None
    # Чем отличается: цифра формата, требуемая версия Студии, сообщения линтера и неизменности.
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def stored(self) -> bool:
        """Версия ляжет в хранилище и будет в каталоге (новая или уже там)."""
        return self.verdict in (Verdict.new, Verdict.present)


@dataclass(frozen=True)
class PlannedPack:
    id: str
    path: str
    name: Mapping[str, str]
    versions: tuple[PlannedVersion, ...]
    conflict: PackConflict | None = None
    # Метка источника, который уже несёт этот пак (при `other_source`).
    conflict_with: str | None = None
    replaces_builtin: bool = False
    problems: tuple[str, ...] = ()

    @property
    def new_versions(self) -> tuple[PlannedVersion, ...]:
        return tuple(v for v in self.versions if v.verdict is Verdict.new)


@dataclass(frozen=True)
class CatalogPlan:
    revision: str
    packs: tuple[PlannedPack, ...]
    problems: tuple[str, ...] = ()

    @property
    def blockers(self) -> tuple[Blocker, ...]:
        found: list[Blocker] = []
        if not self.packs:
            found.append(Blocker.no_packs)
        if any(p.conflict is not None for p in self.packs):
            found.append(Blocker.pack_conflict)
        versions = [v for p in self.packs for v in p.versions]
        if any(v.verdict is Verdict.changed for v in versions):
            found.append(Blocker.version_changed)
        if any(v.verdict is Verdict.invalid and v.errors and v.digest is not None for v in versions):
            found.append(Blocker.version_invalid)
        return tuple(found)

    @property
    def ok(self) -> bool:
        return not self.blockers

    @property
    def new_count(self) -> int:
        return sum(len(p.new_versions) for p in self.packs)


@dataclass(frozen=True)
class ExistingPack:
    """Пак, который уже есть в каталоге Студии: откуда он и жив ли его источник."""

    origin: PackOrigin
    # Источник пака существует (включён или выключен); у вшитого всегда True.
    source_alive: bool = True


def plan_catalog(  # noqa: PLR0913 — всё, что нужно плану, явными аргументами
    tree: InspectedTree,
    *,
    revision: str,
    source_id: str,
    replace_builtin: bool,
    existing: Mapping[str, ExistingPack],
    existing_digest: Callable[[str, str, str], str | None],
    app_version: str | None,
    labels: Mapping[str, str] | None = None,
) -> CatalogPlan:
    """`existing` паки каталога (вшитые и подключённые, в том числе скрытые) по id; `existing_digest` дайджест
    версии, которая уже есть в каталоге (None: такой нет); `labels` метки источников по id для текста конфликта."""
    packs = tuple(
        _plan_pack(
            pack,
            source_id=source_id,
            replace_builtin=replace_builtin,
            existing=existing,
            existing_digest=existing_digest,
            app_version=app_version,
            labels=labels or {},
        )
        for pack in tree.packs
    )
    return CatalogPlan(revision=revision, packs=packs, problems=tree.problems)


def _plan_pack(  # noqa: PLR0913 — те же аргументы, что у плана
    pack: InspectedPack,
    *,
    source_id: str,
    replace_builtin: bool,
    existing: Mapping[str, ExistingPack],
    existing_digest: Callable[[str, str, str], str | None],
    app_version: str | None,
    labels: Mapping[str, str],
) -> PlannedPack:
    conflict, conflict_with, replaces = _conflict(pack, source_id, replace_builtin, existing, labels)
    versions = tuple(
        _plan_version(pack.id, version, existing_digest, app_version)
        for template in pack.templates
        for version in sorted(template.versions, key=_version_order)
    )
    problems = pack.problems + tuple(problem for template in pack.templates for problem in template.problems)
    return PlannedPack(
        id=pack.id,
        path=pack.path,
        name=pack.name,
        versions=versions,
        conflict=conflict,
        conflict_with=conflict_with,
        replaces_builtin=replaces,
        problems=problems,
    )


def _conflict(
    pack: InspectedPack,
    source_id: str,
    replace_builtin: bool,
    existing: Mapping[str, ExistingPack],
    labels: Mapping[str, str],
) -> tuple[PackConflict | None, str | None, bool]:
    if not pack.readable or not is_store_name(pack.id):
        return PackConflict.invalid, None, False
    current = existing.get(pack.id)
    if current is None:
        return None, None, False
    origin = current.origin
    if origin.kind is PackOriginKind.builtin or origin.replaces_builtin:
        # Пак вшит в Студию (или уже заменяет вшитый): заменить можно только явной галочкой.
        if origin.kind is PackOriginKind.subscribed and origin.source_id != source_id and current.source_alive:
            return PackConflict.other_source, labels.get(origin.source_id or "") or origin.label, False
        return (None, None, True) if replace_builtin else (PackConflict.builtin, None, False)
    if origin.source_id == source_id or not current.source_alive:
        # Свой пак или пак удалённого источника: удалённый источник выбора не требует.
        return None, None, False
    return PackConflict.other_source, labels.get(origin.source_id or "") or origin.label, False


def _version_order(version: InspectedVersion) -> tuple[int, ...]:
    key = parse_version_key(version.version)
    return key if key is not None else (0, 0, 0)


def _plan_version(
    pack_id: str,
    version: InspectedVersion,
    existing_digest: Callable[[str, str, str], str | None],
    app_version: str | None,
) -> PlannedVersion:
    verdict, errors = _verdict(pack_id, version, existing_digest, app_version)
    return PlannedVersion(
        template=version.template,
        version=version.version,
        verdict=verdict,
        digest=version.digest,
        kind=version.kind,
        min_studio=version.min_studio,
        errors=errors,
        warnings=version.warnings,
    )


def _verdict(
    pack_id: str,
    version: InspectedVersion,
    existing_digest: Callable[[str, str, str], str | None],
    app_version: str | None,
) -> tuple[Verdict, tuple[str, ...]]:
    if not version.released:
        return Verdict.unreleased, ()
    if version.digest is None or version.digest != version.registry_digest:
        return Verdict.invalid, (*version.errors, _changed_since_release(version))
    current = existing_digest(pack_id, version.template, version.version)
    if current is not None:
        return (Verdict.present if current == version.digest else Verdict.changed), ()
    return _new_version_verdict(version, app_version)


def _new_version_verdict(version: InspectedVersion, app_version: str | None) -> tuple[Verdict, tuple[str, ...]]:
    too_new = _too_new(version, app_version)
    if too_new:
        return Verdict.incompatible, (too_new,)
    if not is_store_name(version.template) or not is_store_name(version.version):
        return Verdict.invalid, ("недопустимое имя шаблона или версии",)
    if version.errors or not version.readable:
        return Verdict.invalid, version.errors or ("лоадер этой Студии не разобрал версию",)
    return Verdict.new, ()


def _changed_since_release(version: InspectedVersion) -> str:
    if version.digest is None:
        return "каталог выпущенной версии отсутствует"
    return (
        f"каталог выпущенной версии изменён после выпуска (реестр {version.registry_digest}, сейчас {version.digest})"
    )


def _too_new(version: InspectedVersion, app_version: str | None) -> str | None:
    if version.manifest_format is not None and version.manifest_format > MANIFEST_FORMAT:
        return f"manifest_format {version.manifest_format}, эта Студия понимает до {MANIFEST_FORMAT}"
    if version.min_studio and not studio_satisfies(version.min_studio, app_version):
        return f"нужна Студия {version.min_studio} или новее"
    return None


def stored_versions(
    plan: CatalogPlan, pack_ids: Collection[str] | None = None
) -> dict[str, tuple[PlannedVersion, ...]]:
    """Версии, которые после «Применить» будут в каталоге, по пакам плана."""
    return {
        pack.id: tuple(v for v in pack.versions if v.stored)
        for pack in plan.packs
        if pack_ids is None or pack.id in pack_ids
    }
