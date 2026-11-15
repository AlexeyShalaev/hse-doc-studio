"""`/api/v1/pack-studio/.../submission`: профили сдачи, пункты и порядок маршрута версии формой (срез T13).

`GET` отдаёт профили `pack_submission` с записями списков по индексам YAML, каталог слотов, анкеты и порядок версии.
`PATCH` применяет правки формы точечными правками `version.yaml` с `If-Match` по ETag манифеста; ответ тот же, что
у `GET`, уже по новому тексту. `POST .../submission/routes` считает «Маршрут в этой комбинации» каждого профиля на
синтетическом проекте предпросмотра (набор данных и переключатели).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Response

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.pack_studio import pack_studio_guard
from hse_doc_studio.api.schemas.pack_studio import ReadOnlyReason
from hse_doc_studio.api.schemas.pack_studio_submission import (
    PackDocSlotRef,
    PackIndexedExtra,
    PackIndexedItem,
    PackIndexedSlot,
    PackProfileRoute,
    PackRoutePair,
    PackRoutePerson,
    PackSkippedPair,
    PackSubmissionExtra,
    PackSubmissionForm,
    PackSubmissionItem,
    PackSubmissionOp,
    PackSubmissionPatchRequest,
    PackSubmissionProfile,
    PackSubmissionResponse,
    PackSubmissionRoutesRequest,
    PackSubmissionRoutesResponse,
    PackSubmissionSlot,
    PackSubmissionSlotInfo,
    PackSubmissionWhen,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.submission import (
    ExtraEntry,
    ItemEntry,
    ProfileHead,
    ProfileRoute,
    ProfileView,
    SlotEntry,
    SubmissionList,
    SubmissionOp,
    SubmissionOpKind,
    WhenCondition,
)
from hse_doc_studio.use_cases.pack_studio.submission import PackSubmissionService, SubmissionView

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

_SUBMISSION = "/pack-studio/workspaces/{workspace_id}/versions/{pack}/{template}/{version}/submission"
_NO_STORE = {"Cache-Control": "no-store"}

IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _when(when: WhenCondition | None) -> PackSubmissionWhen | None:
    return PackSubmissionWhen.model_validate({"person": when.person, "role": when.role}) if when else None


def _item(entry: ItemEntry | None) -> PackSubmissionItem | None:
    if entry is None:
        return None
    return PackSubmissionItem.model_validate(
        {
            "doc_id": entry.doc_id,
            "signatures": list(entry.signatures),
            "methods": {slot: list(methods) for slot, methods in entry.methods},
            "skip_if_nda": entry.skip_if_nda,
            "supported_kinds": list(entry.supported_kinds),
        }
    )


def _extra(entry: ExtraEntry | None) -> PackSubmissionExtra | None:
    if entry is None:
        return None
    return PackSubmissionExtra.model_validate(
        {
            "source": entry.source,
            "output_name": entry.output_name,
            "format": entry.format,
            "supported_kinds": list(entry.supported_kinds),
        }
    )


def _slot(entry: SlotEntry | None) -> PackSubmissionSlot | None:
    if entry is None:
        return None
    return PackSubmissionSlot(
        doc_id=entry.doc_id, slot_id=entry.slot_id, when=_when(entry.when), optional=entry.optional
    )


def _steps(steps: tuple[tuple[str, ...], ...] | None) -> list[list[str]] | None:
    return [list(step) for step in steps] if steps is not None else None


def _profile(view: ProfileView) -> PackSubmissionProfile:
    return PackSubmissionProfile(
        index=view.index,
        id=view.id,
        name=dict(view.name),
        description=dict(view.description),
        deadline_hint=dict(view.deadline_hint) if view.deadline_hint is not None else None,
        items=[PackIndexedItem(index=i.index, entry=_item(i.entry), error=i.error) for i in view.items],
        extra_items=[PackIndexedExtra(index=i.index, entry=_extra(i.entry), error=i.error) for i in view.extra_items],
        signing_route=_steps(view.signing_route),
        signing_slots=[PackIndexedSlot(index=i.index, entry=_slot(i.entry), error=i.error) for i in view.signing_slots],
        error=view.error,
    )


def submission_response(workspace_id: UUID, view: SubmissionView) -> PackSubmissionResponse:
    sub = view.submission
    read_only: ReadOnlyReason | None = (
        "version_released" if view.read_only == "version_released" else "releases_read_only" if view.read_only else None
    )
    return PackSubmissionResponse.model_validate(
        {
            "workspace_id": str(workspace_id),
            "pack": view.ref.pack,
            "template": view.ref.template,
            "version": view.ref.version,
            "path": view.path,
            "etag": view.etag,
            "read_only": read_only,
            "documents": list(sub.documents),
            "supported_kinds": list(sub.supported_kinds),
            "has_nda": sub.has_nda,
            "slots": [
                PackSubmissionSlotInfo(
                    id=s.id,
                    label=dict(s.label),
                    applies_to=list(s.applies_to),
                    required=s.required,
                    per_author=s.per_author,
                )
                for s in sub.slots
            ],
            "forms": [
                PackSubmissionForm(
                    id=f.id,
                    title=dict(f.title),
                    source=f.source,
                    output_name=f.output_name,
                    format=f.format,
                    required_for_pack=f.required_for_pack,
                )
                for f in sub.forms
            ],
            "route": _steps(sub.route),
            "builtin_route": _steps(sub.builtin_route),
            "profiles": [_profile(p) for p in sub.profiles],
        }
    )


def _value(body: PackSubmissionOp) -> dict[str, Any] | None:
    entry = {"items": body.item, "extra_items": body.extra, "signing_slots": body.slot}.get(body.entries or "")
    return entry.model_dump() if entry is not None else None


def _op(body: PackSubmissionOp) -> SubmissionOp:
    head = body.head
    return SubmissionOp(
        op=SubmissionOpKind(body.op),
        profile=body.profile,
        head=ProfileHead(head.id, head.name, head.description, head.deadline_hint) if head is not None else None,
        entries=SubmissionList(body.entries) if body.entries is not None else None,
        index=body.index,
        to=body.to,
        value=_value(body),
        steps=tuple(tuple(step) for step in body.steps) if body.steps is not None else None,
    )


def _route(route: ProfileRoute) -> PackProfileRoute:
    return PackProfileRoute.model_validate(
        {
            "id": route.id,
            "steps": [
                [PackRoutePerson.model_validate({"persona": p.persona, "role": p.role, "name": p.name}) for p in step]
                for step in route.steps
            ],
            "pairs": [
                PackRoutePair.model_validate(
                    {
                        "doc_id": p.doc_id,
                        "slot_id": p.slot_id,
                        "persona": p.persona,
                        "source": p.source.value,
                        "optional": p.optional,
                        "when": _when(p.when),
                    }
                )
                for p in route.pairs
            ],
            "skipped": [PackSkippedPair(doc_id=p.doc_id, slot_id=p.slot_id, when=_when(p.when)) for p in route.skipped],
            "may_add": [PackDocSlotRef(doc_id=doc, slot_id=slot) for doc, slot in route.may_add],
            "items_off": list(route.items_off),
            "order_source": route.order_source,
            "preset": route.preset,
        }
    )


@router.get(_SUBMISSION, response_model=PackSubmissionResponse)
async def get_submission(  # noqa: PLR0913 — путь версии
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    submission: FromDishka[PackSubmissionService],
    response: Response,
) -> PackSubmissionResponse:
    """Профили сдачи версии, каталог слотов, анкеты и порядок маршрута (5.5, 5.6)."""
    view = await submission.get(require_actor(), workspace_id, pack, template, version)
    response.headers.update({"ETag": view.etag, **_NO_STORE})
    return submission_response(workspace_id, view)


@router.patch(_SUBMISSION, response_model=PackSubmissionResponse)
async def patch_submission(  # noqa: PLR0913 — путь версии, тело и версия файла
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackSubmissionPatchRequest,
    submission: FromDishka[PackSubmissionService],
    response: Response,
    if_match: IfMatch = None,
) -> PackSubmissionResponse:
    """Правки профилей и порядка в `version.yaml` (весь набор или ничего); выпущенная версия: `version_released`."""
    view = await submission.edit(
        require_actor(), workspace_id, pack, template, version, [_op(op) for op in body.ops], if_match
    )
    response.headers.update({"ETag": view.etag, **_NO_STORE})
    return submission_response(workspace_id, view)


@router.post(f"{_SUBMISSION}/routes", response_model=PackSubmissionRoutesResponse)
async def submission_routes(  # noqa: PLR0913 — путь версии и комбинация
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackSubmissionRoutesRequest,
    submission: FromDishka[PackSubmissionService],
    response: Response,
) -> PackSubmissionRoutesResponse:
    """«Маршрут в этой комбинации» каждого профиля (5.6) на синтетическом проекте набора и переключателей."""
    routes = await submission.routes(
        require_actor(), workspace_id, pack, template, version, body.example, body.combination
    )
    response.headers.update(_NO_STORE)
    return PackSubmissionRoutesResponse(
        example=routes.example,
        combination=dict(routes.combination),
        profiles=[_route(r) for r in routes.profiles],
    )
