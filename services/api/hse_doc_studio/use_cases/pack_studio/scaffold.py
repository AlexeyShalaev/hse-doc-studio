"""Пак и шаблон с нуля (docs/design/template-studio.md, раздел 8; срез T15).

- Окно «Новый пак» и «Новый шаблон» спрашивает `options`: источники копии (паки пространства и каталога этой
  Студии), занятые id паков, сопровождающий из профиля, лицензия и номер первой версии по умолчанию.
- `create_pack`: id пака уникален в пространстве и среди паков каталога Студии (вшитых и подключённых), иначе
  `pack_id_taken`; внутри один шаблон из заготовки «Минимальный» или копии выбранной версии.
- `create_template`: новый шаблон в существующем паке пространства, то же на уровне шаблона.

Файлы пишутся под замком пространства (`workspace_busy` второй, как у мастера «Новая версия»). У git это правки
рабочего дерева: в коммит и PR их кладёт «Сохранить версию» или «Предложить изменения» (T6).
"""

from __future__ import annotations

import asyncio
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import PackInfo, TemplateInfo
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.protocols import IPackScaffolder
from hse_doc_studio.core.pack_studio.scaffold import (
    DEFAULT_LICENSE,
    TEXT_MAX,
    CopySource,
    Maintainer,
    NewPack,
    NewTemplate,
    Scaffold,
    ScaffoldKind,
    ScaffoldOptions,
    ScaffoldResult,
    SourceMeta,
    SourceOrigin,
    SourcePack,
    SourceTemplate,
    SourceVersion,
    check_pack_id,
    check_template_id,
    check_version_number,
    clean_localized,
    default_version,
)
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

_EXAMPLES = "examples"
_VERSIONS = "versions"


def _today() -> date:
    return datetime.now(DISPLAY_ZONE).date()


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


@dataclass(frozen=True)
class CreatePackInput:
    pack: NewPack
    scaffold: Scaffold = Scaffold()
    version: str | None = None


@dataclass(frozen=True)
class CreateTemplateInput:
    template: NewTemplate
    scaffold: Scaffold = Scaffold()
    version: str | None = None


class PackScaffoldService:
    def __init__(
        self,
        workspaces: PackWorkspaceService,
        scaffolder: IPackScaffolder,
        templates: ITemplateRepository,
        *,
        maintainer: Callable[[], Maintainer | None] | None = None,
        today: Callable[[], date] = _today,
    ) -> None:
        self._workspaces = workspaces
        self._scaffolder = scaffolder
        self._templates = templates
        self._maintainer = maintainer
        self._today = today

    async def options(self, actor: Actor, workspace_id: UUID) -> ScaffoldOptions:
        _, root = await self._workspaces.ready(actor, workspace_id)
        local = await asyncio.to_thread(self._scaffolder.sources, root)
        dirs = await asyncio.to_thread(self._scaffolder.pack_dirs, root)
        catalog = self._catalog_packs()
        taken = sorted(dirs | {_fold(p.id) for p in catalog})
        return ScaffoldOptions(
            sources=(*local, *(self._catalog_source(p) for p in catalog)),
            taken_packs=tuple(taken),
            maintainer=self._default_maintainer(),
            license=DEFAULT_LICENSE,
            version=default_version(self._today()),
        )

    async def create_pack(self, actor: Actor, workspace_id: UUID, inp: CreatePackInput) -> ScaffoldResult:
        pack = _clean_pack(inp.pack)
        version = check_version_number(inp.version) if inp.version else default_version(self._today())
        if _fold(pack.id) in {_fold(p.id) for p in self._catalog_packs()}:
            raise PackStudioError(PackStudioErrorCode.pack_id_taken, id=pack.id, where="studio")
        ws, root = await self._workspaces.ready(actor, workspace_id)

        async def work() -> ScaffoldResult:
            source = await self._source(root, inp.scaffold)
            return await asyncio.to_thread(
                lambda: self._scaffolder.create_pack(root, pack, version=version, today=self._today(), source=source)
            )

        return await self._workspaces.tasks.exclusive(ws.id, work)

    async def create_template(
        self, actor: Actor, workspace_id: UUID, pack: str, inp: CreateTemplateInput
    ) -> ScaffoldResult:
        template = _clean_template(inp.template)
        version = check_version_number(inp.version) if inp.version else default_version(self._today())
        ws, root = await self._workspaces.ready(actor, workspace_id)

        async def work() -> ScaffoldResult:
            source = await self._source(root, inp.scaffold)
            return await asyncio.to_thread(
                lambda: self._scaffolder.create_template(
                    root, pack, template, version=version, today=self._today(), source=source
                )
            )

        return await self._workspaces.tasks.exclusive(ws.id, work)

    # ── служебное ────────────────────────────────────────────────────────────

    def _default_maintainer(self) -> Maintainer | None:
        if self._maintainer is None:
            return None
        try:
            return self._maintainer()
        except Exception:  # noqa: BLE001 — подсказка формы, без неё окно работает
            return None

    def _catalog_source(self, pack: PackInfo) -> SourcePack:
        return SourcePack(
            origin=SourceOrigin.catalog,
            pack=pack.id,
            name=dict(pack.name),
            license=pack.license,
            templates=tuple(self._catalog_template(pack, t) for t in pack.templates),
        )

    def _catalog_template(self, pack: PackInfo, template: TemplateInfo) -> SourceTemplate:
        """Версии шаблона каталога, видимые мастеру проекта (все выпущены), новые первыми."""
        default = template.default_version or None
        versions = sorted(
            (v for v in self._templates.list_versions(pack.id, template.id) if v not in template.hidden_versions),
            key=lambda v: parse_version_key(v) or (0, 0, 0),
        )
        return SourceTemplate(
            template=template.id,
            name=dict(template.name),
            default_version=default,
            versions=tuple(
                SourceVersion(version=v, status=None, released=True, default=v == default) for v in reversed(versions)
            ),
        )

    def _catalog_packs(self) -> list[PackInfo]:
        return [p for p in self._templates.list_packs() if p.listed]

    async def _source(self, root: Path, scaffold: Scaffold) -> CopySource | None:
        if scaffold.kind is ScaffoldKind.minimal:
            return None
        source = scaffold.source
        if source is None:
            raise PackStudioError(PackStudioErrorCode.version_not_found)
        if source.origin is SourceOrigin.workspace:
            return await asyncio.to_thread(self._scaffolder.workspace_source, root, source)
        return self._catalog_copy(source.pack, source.template, source.version)

    def _catalog_copy(self, pack_id: str, template_id: str, version: str) -> CopySource:
        """Версия каталога этой Студии: каталог версии (вшитый или в хранилище подключённых) и сведения об источнике."""
        pack = next((p for p in self._catalog_packs() if p.id == pack_id), None)
        template = next((t for t in pack.templates if t.id == template_id), None) if pack else None
        if pack is None or template is None or version in template.hidden_versions:
            raise PackStudioError(PackStudioErrorCode.version_not_found, version=version)
        version_dir = self._templates.version_dir(pack.id, template.id, version)
        if version_dir is None:
            raise PackStudioError(PackStudioErrorCode.version_not_found, version=version)
        fields: dict[str, object] = {"icon": template.icon, "accent_hue": template.accent_hue}
        examples = version_dir.parent.parent / _EXAMPLES if version_dir.parent.name == _VERSIONS else None
        return CopySource(
            origin=SourceOrigin.catalog,
            version_dir=version_dir,
            examples_dir=examples,
            meta=SourceMeta(
                pack=pack.id,
                template=template.id,
                version=version,
                pack_name=dict(pack.name),
                license=pack.license,
                maintainer=pack.maintainer.get("name", ""),
                template_fields=fields,
            ),
        )


def _clean_pack(pack: NewPack) -> NewPack:
    name = clean_localized(pack.name, required=True, field_name="name") or {}
    maintainer = pack.maintainer
    if maintainer is not None:
        maintainer = Maintainer(
            name=maintainer.name.strip()[:TEXT_MAX],
            email=maintainer.email.strip()[:TEXT_MAX],
            url=maintainer.url.strip()[:TEXT_MAX],
        )
    return replace(
        pack,
        id=check_pack_id(pack.id),
        name=name,
        description=clean_localized(pack.description, required=False, field_name="description"),
        maintainer=maintainer if maintainer is not None and maintainer.name else None,
        license=(pack.license or "").strip()[:TEXT_MAX] or DEFAULT_LICENSE,
        source=(pack.source or "").strip()[:TEXT_MAX] or None,
        template=_clean_template(pack.template),
    )


def _clean_template(template: NewTemplate) -> NewTemplate:
    return replace(
        template,
        id=check_template_id(template.id),
        name=clean_localized(template.name, required=True, field_name="template_name") or {},
        short_name=clean_localized(template.short_name, required=False, field_name="short_name"),
        description=clean_localized(template.description, required=False, field_name="template_description"),
    )
