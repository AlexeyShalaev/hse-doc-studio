"""Места подписей и метки даты версии шаблона на PDF предпросмотра (docs/design/template-studio.md, 5.6, срез T9).

Каталог слотов и записи мест читаются из `version.yaml` версии, рамки документа сборки считаются по её якорям.
Правка идёт под замком пространства с `If-Match` по ETag манифеста (`PackFilesService.edit_yaml`): выпущенная версия
отвечает `version_released`, чужая правка между чтением и записью `stale_file`. Невыполнимая правка мест
(`PlaceEditError`) это `place_invalid` с причиной по-английски, файл не меняется.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import VERSION_MANIFEST, VersionRef
from hse_doc_studio.core.pack_studio.places import MAX_PLACE_OPS, PlaceEditError, PlaceOp, VersionPlaces
from hse_doc_studio.core.pack_studio.preview import PreviewBuild
from hse_doc_studio.core.pack_studio.protocols import IPackPlaces
from hse_doc_studio.core.signatures.anchors import BuildAnchors
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, version_ref


@dataclass(frozen=True)
class PlacesView:
    """Места версии: манифест (путь, ETag, почему только чтение), сборка, по якорям которой посчитаны рамки."""

    ref: VersionRef
    path: str
    etag: str
    read_only: str | None
    build: PreviewBuild | None
    places: VersionPlaces


class PackPlacesService:
    def __init__(self, files: PackFilesService, previews: PackPreviewService, places: IPackPlaces) -> None:
        self._files = files
        self._previews = previews
        self._places = places

    async def get(  # noqa: PLR0913 — путь версии и сборка
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str, build_id: UUID | None
    ) -> PlacesView:
        ref = version_ref(pack, template, version)
        path = _manifest(ref)
        found = await self._files.read(actor, workspace_id, path)
        build, anchors = await self._source(actor, workspace_id, build_id, ref)
        text = _text(found.content)
        places = await asyncio.to_thread(self._describe, text, build, anchors)
        return PlacesView(ref, path, found.etag, found.read_only, build, places)

    async def edit(  # noqa: PLR0913 — путь версии, сборка, правки и версия файла
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        build_id: UUID | None,
        ops: Sequence[PlaceOp],
        if_match: str | None,
    ) -> PlacesView:
        if not 0 < len(ops) <= MAX_PLACE_OPS:
            raise PackStudioError(PackStudioErrorCode.place_invalid, reason=f"1..{MAX_PLACE_OPS} operations")
        ref = version_ref(pack, template, version)
        path = _manifest(ref)
        build, anchors = await self._source(actor, workspace_id, build_id, ref)
        document = build.document if build is not None else None

        def edit(text: str) -> str:
            try:
                return self._places.apply(text, ops, document=document, anchors=anchors)
            except PlaceEditError as exc:
                raise PackStudioError(PackStudioErrorCode.place_invalid, reason=str(exc)[:300]) from None
            except (TypeError, ValueError) as exc:
                raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None

        written = await self._files.edit_yaml(actor, workspace_id, path, edit, if_match)
        text = written.content or ""
        places = await asyncio.to_thread(self._describe, text, build, anchors)
        return PlacesView(ref, path, file_etag(text.encode("utf-8")), None, build, places)

    async def _source(
        self, actor: Actor, workspace_id: UUID, build_id: UUID | None, ref: VersionRef
    ) -> tuple[PreviewBuild | None, BuildAnchors | None]:
        if build_id is None:
            return None, None
        return await self._previews.places_source(actor, workspace_id, build_id, ref)

    def _describe(self, text: str, build: PreviewBuild | None, anchors: BuildAnchors | None) -> VersionPlaces:
        try:
            return self._places.describe(text, document=build.document if build else None, anchors=anchors)
        except (TypeError, ValueError) as exc:
            raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None


def _manifest(ref: VersionRef) -> str:
    return f"{ref.dir}/{VERSION_MANIFEST}"


def _text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        raise PackStudioError(PackStudioErrorCode.version_unreadable, reason="version.yaml is not UTF-8") from None
