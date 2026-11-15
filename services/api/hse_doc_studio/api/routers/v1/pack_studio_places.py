"""`/api/v1/pack-studio/.../signatures`: места подписей и метки даты версии на PDF предпросмотра (срез T9).

`GET` отдаёт каталог слотов версии с записями мест и, если передана сборка предпросмотра (`build_id`), рамки её
документа по её якорям. `PATCH` применяет правки мест (`set_place`, `make_default`, `add_date` и другие) точечными
правками `version.yaml` с `If-Match` по ETag манифеста; ответ тот же, что у `GET`, уже по новому тексту.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Query, Response

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.pack_studio import pack_studio_guard
from hse_doc_studio.api.routers.v1.signatures import pack_date_response, pack_place_response
from hse_doc_studio.api.schemas.pack_studio import (
    PackFrameDate,
    PackIndexedDate,
    PackMarkBox,
    PackPlaceBox,
    PackPlaceOp,
    PackSignaturesBuild,
    PackSignatureSlot,
    PackSignaturesPatchRequest,
    PackSignaturesResponse,
    PackSlotFrame,
    ReadOnlyReason,
)
from hse_doc_studio.api.schemas.signature import PlaceAnchorResponse
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.catalog import SignatureDefaultDate, SignatureDefaultPlacement
from hse_doc_studio.core.pack_studio.places import (
    AnchorRef,
    DocFrame,
    MarkBox,
    PlaceBox,
    PlaceOp,
    PlaceOpKind,
    SlotPlaces,
)
from hse_doc_studio.use_cases.pack_studio.places import PackPlacesService, PlacesView

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

_PLACES = "/pack-studio/workspaces/{workspace_id}/versions/{pack}/{template}/{version}/signatures"
_NO_STORE = {"Cache-Control": "no-store"}

IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _box(place: SignatureDefaultPlacement | None) -> PackPlaceBox | None:
    if place is None:
        return None
    return PackPlaceBox(page=place.page, x_mm=place.x_mm, y_mm=place.y_mm, width_mm=place.width_mm)


def _mark(mark: SignatureDefaultDate | None) -> PackMarkBox | None:
    if mark is None:
        return None
    return PackMarkBox(
        page=mark.page,
        x_mm=mark.x_mm,
        y_mm=mark.y_mm,
        width_mm=mark.width_mm,
        height_mm=mark.height_mm,
        format=mark.format,
        align=mark.align,
    )


def _anchor(ref: AnchorRef | None) -> PlaceAnchorResponse | None:
    return PlaceAnchorResponse(id=ref.id, state=ref.state) if ref is not None else None


def _frame(frame: DocFrame | None) -> PackSlotFrame | None:
    if frame is None:
        return None
    return PackSlotFrame(
        kind=frame.kind.value,
        entry=pack_place_response(frame.entry),
        box=_box(frame.box),
        anchor=_anchor(frame.anchor),
        dates=[
            PackFrameDate(index=d.index, entry=pack_date_response(d.entry), box=_mark(d.box), anchor=_anchor(d.anchor))
            for d in frame.dates
        ],
    )


def _slot(slot: SlotPlaces) -> PackSignatureSlot:
    return PackSignatureSlot(
        id=slot.id,
        label=slot.label,
        applies_to=list(slot.applies_to),
        per_author=slot.per_author,
        required=slot.required,
        default_place=pack_place_response(slot.default_place),
        default_set=slot.default_set,
        places={doc: pack_place_response(entry) for doc, entry in slot.places},
        dates={
            doc: [PackIndexedDate(index=i, entry=pack_date_response(m)) for i, m in marks] for doc, marks in slot.dates
        },
        document=_frame(slot.document),
    )


def places_response(workspace_id: UUID, view: PlacesView) -> PackSignaturesResponse:
    places = view.places
    build = view.build
    read_only: ReadOnlyReason | None = (
        "version_released" if view.read_only == "version_released" else "releases_read_only" if view.read_only else None
    )
    return PackSignaturesResponse(
        workspace_id=str(workspace_id),
        pack=view.ref.pack,
        template=view.ref.template,
        version=view.ref.version,
        path=view.path,
        etag=view.etag,
        read_only=read_only,
        documents=list(places.documents),
        build=PackSignaturesBuild(
            id=str(build.id),
            document=build.document,
            anchors_known=places.anchors_known,
            sign_anchors=list(places.sign_anchors),
            date_anchors=list(places.date_anchors),
        )
        if build is not None
        else None,
        slots=[_slot(slot) for slot in places.slots],
    )


def _op(body: PackPlaceOp) -> PlaceOp:
    box = body.box
    mark = body.mark
    return PlaceOp(
        op=PlaceOpKind(body.op),
        slot=body.slot,
        doc=body.doc,
        box=PlaceBox(box.page, box.x_mm, box.y_mm, box.width_mm) if box is not None else None,
        index=body.index,
        mark=MarkBox(mark.page, mark.x_mm, mark.y_mm, mark.width_mm, mark.height_mm, mark.format, mark.align)
        if mark is not None
        else None,
        anchor=body.anchor,
    )


@router.get(_PLACES, response_model=PackSignaturesResponse)
async def get_places(  # noqa: PLR0913 — путь версии и сборка
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    places: FromDishka[PackPlacesService],
    response: Response,
    build_id: Annotated[UUID | None, Query()] = None,
) -> PackSignaturesResponse:
    """Каталог слотов версии и рамки документа сборки `build_id` по её якорям (5.6)."""
    view = await places.get(require_actor(), workspace_id, pack, template, version, build_id)
    response.headers.update({"ETag": view.etag, **_NO_STORE})
    return places_response(workspace_id, view)


@router.patch(_PLACES, response_model=PackSignaturesResponse)
async def patch_places(  # noqa: PLR0913 — путь версии, тело и версия файла
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackSignaturesPatchRequest,
    places: FromDishka[PackPlacesService],
    response: Response,
    if_match: IfMatch = None,
) -> PackSignaturesResponse:
    """Правки мест и меток даты в `version.yaml` (весь набор или ничего); выпущенная версия: `version_released`."""
    view = await places.edit(
        require_actor(),
        workspace_id,
        pack,
        template,
        version,
        body.build_id,
        [_op(op) for op in body.ops],
        if_match,
    )
    response.headers.update({"ETag": view.etag, **_NO_STORE})
    return places_response(workspace_id, view)
