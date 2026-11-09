"""Задача подписанта маршрута подписания (docs/design/signing-route.md, разделы 3.2, 7 и 8): страница `/sign/...`.

Только сервер: локальная Студия отвечает 404 (раздел 6.9). Гард по таблице `ROUTE_ACTIONS` требует `OUTPUT_READ`;
задачу видит и действует только участник маршрута (остальным 404, как и гостю или ссылочному праву), право `SIGN`
на каждый свой слот проверяет сценарий. Все действия отвечают задачей: клиент кладёт ответ в кэш без повторного
чтения.
"""

from __future__ import annotations

from typing import cast
from urllib.parse import quote
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.route_actions import API_PREFIX
from hse_doc_studio.api.routers.v1.signing_routes import event_response, key_failure, key_id, key_info, reader
from hse_doc_studio.api.schemas import signing_route as s
from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.plan import SignMethod
from hse_doc_studio.core.signatures.signer_profile import MAX_PROFILE_IMAGE_BYTES, MAX_PROFILE_KEY_BYTES
from hse_doc_studio.core.signing_route.entities import RouteConflictError, RouteInputError
from hse_doc_studio.core.signing_route.signer import InvalidFileError
from hse_doc_studio.core.value_objects import SignerInfo
from hse_doc_studio.use_cases.signing_route.key_signer import KeyRequest
from hse_doc_studio.use_cases.signing_route.signer import ApproveRequest, SigningTaskScenario, SignRequest
from hse_doc_studio.use_cases.signing_route.task_view import TaskDetails, TaskDoc, TaskSlot

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(require_server_mode)])

_TASK = "/projects/{project_id}/signing-routes/{route_id}/task"
_PLATE_KINDS = ("x509", "openpgp", "manual")


# --- ответ ----------------------------------------------------------------------------------------------------------


def _pdf_url(project_id: UUID, doc: TaskDoc) -> str:
    """До фиксации предпросмотр с подписями (без придержанных картинок), после неё зафиксированный PDF."""
    base = f"{API_PREFIX}/projects/{project_id}/docs/{quote(doc.doc_id, safe='')}"
    return f"{base}/frozen/pdf" if doc.frozen else f"{base}/pdf/signed"


def _other_slot(slot: TaskSlot) -> s.SigningTaskOtherSlot:
    return s.SigningTaskOtherSlot(
        slot_id=slot.slot_id,
        label=slot.label,
        page=max(slot.page, 1),
        x_mm=slot.x_mm,
        y_mm=slot.y_mm,
        width_mm=slot.width_mm,
        height_mm=slot.height_mm,
        mark=slot.mark.value,
        status=slot.status.value,
    )


def _own_slot(slot: TaskSlot) -> s.SigningTaskSlot:
    return s.SigningTaskSlot(
        **_other_slot(slot).model_dump(), reason=slot.reason.value if slot.reason is not None else None
    )


def _plate(signer: SignerInfo | None) -> s.SigningPlate | None:
    if signer is None:
        return None
    kind = cast(s.SigningPlateKindName, signer.kind if signer.kind in _PLATE_KINDS else "manual")
    return s.SigningPlate(owner=signer.owner, kind=kind, cert_id=signer.cert_id)


def task_response(task: TaskDetails) -> s.SigningTask:
    route = task.route
    return s.SigningTask(
        route=s.SigningTaskRoute(
            id=str(route.id),
            project=s.SigningProjectRef(id=str(route.project_id), name=task.project_name),
            profile=s.SigningProfileRef(id=route.profile_id, name=task.profile_name),
            status=task.status.value,
            phase=task.phase.value if task.phase is not None else None,
            round=route.round,
            current_step=task.current_step,
            deadline=route.deadline,
            message=route.message,
            sender=task.sender_name,
            sent_at=route.sent_at,
            stop_reason=task.stop_reason.value if task.stop_reason is not None else None,
        ),
        steps=[
            [
                s.SigningTaskPerson(
                    name=person.name, persona=person.persona, state=person.state.value, at=person.at, me=person.me
                )
                for person in step
            ]
            for step in task.steps
        ],
        me=s.SigningTaskMe(
            participant_id=str(task.participant.id),
            state=task.view.state.value,
            next_action=task.view.next_action.value,
            methods=[m.value for m in task.methods],
            method=task.method.value if task.method is not None else None,
            image_ready=task.image_ready,
            plate=_plate(task.plate),
            keys=s.SigningTaskKeys(
                server_keys_allowed=task.keys.server_keys_allowed, default_key=key_info(task.keys.default_key)
            ),
        ),
        docs=[
            s.SigningTaskDoc(
                doc_id=doc.doc_id,
                name=doc.name,
                pdf_url=_pdf_url(route.project_id, doc),
                frozen=doc.frozen,
                token=doc.token,
                mine=[_own_slot(slot) for slot in doc.mine],
                others=[_other_slot(slot) for slot in doc.others],
            )
            for doc in task.docs
        ],
        events=[event_response(e) for e in task.events],
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


async def _upload(file: UploadFile, limit: int) -> bytes:
    """Файл целиком, но не больше `limit`: лишнее не читаем, отказ отдаёт сценарий своим текстом."""
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise InvalidFileError(localized_error("Файл слишком большой", "The file is too large"))
    return content


# --- маршруты -------------------------------------------------------------------------------------------------------


@router.get(_TASK, response_model=s.SigningTask)
async def get_signing_task(
    project_id: UUID, route_id: UUID, response: Response, uc: FromDishka[SigningTaskScenario]
) -> s.SigningTask:
    actor = reader()
    _no_store(response)
    return task_response(await uc.get(actor, project_id, route_id))


@router.post(_TASK + "/approve", response_model=s.SigningTask)
async def approve_signing_task(
    project_id: UUID, route_id: UUID, body: s.ApproveSigningTaskRequest, uc: FromDishka[SigningTaskScenario]
) -> s.SigningTask:
    """Согласовать; `method` сменить способ своих слотов; `sign` для «Согласовать и подписать»."""
    actor = reader()
    sign = None
    if body.sign is not None:
        sign = KeyRequest(identity_id=key_id(body.sign.identity_id), passphrase=body.sign.passphrase or "")
    request = ApproveRequest(
        expected=dict(body.expected), method=SignMethod(body.method) if body.method is not None else None, sign=sign
    )
    try:
        task = await uc.approve(actor, project_id, route_id, request)
    except (RouteInputError, RouteConflictError, NotFoundError):
        raise
    except (ValueError, PermissionError, ProjectForbiddenError) as exc:
        key_failure(exc)
    return task_response(task)


@router.post(_TASK + "/sign", response_model=s.SigningTask)
async def sign_signing_task(
    project_id: UUID, route_id: UUID, body: s.SignSigningTaskRequest, uc: FromDishka[SigningTaskScenario]
) -> s.SigningTask:
    """Подписать свои слоты ЭП над зафиксированным PDF ключом Студии."""
    actor = reader()
    key = KeyRequest(identity_id=key_id(body.identity_id), passphrase=body.passphrase or "")
    try:
        task = await uc.sign(actor, project_id, route_id, SignRequest(expected=dict(body.expected), key=key))
    except (RouteInputError, RouteConflictError, NotFoundError):
        raise
    except (ValueError, PermissionError, ProjectForbiddenError) as exc:
        key_failure(exc)
    return task_response(task)


@router.post(_TASK + "/return", response_model=s.SigningTask)
async def return_signing_task(
    project_id: UUID, route_id: UUID, body: s.ReturnSigningTaskRequest, uc: FromDishka[SigningTaskScenario]
) -> s.SigningTask:
    """Вернуть на доработку с обязательным комментарием."""
    return task_response(await uc.return_for_rework(reader(), project_id, route_id, body.comment))


@router.post(_TASK + "/image", response_model=s.SigningTask)
async def upload_signing_task_image(
    project_id: UUID,
    route_id: UUID,
    uc: FromDishka[SigningTaskScenario],
    file: UploadFile = File(...),
    remember: bool = Form(default=False),
) -> s.SigningTask:
    """Своя картинка подписи (PNG); `remember` сохраняет её в профиль подписанта для других проектов."""
    actor = reader()
    png = await _upload(file, MAX_PROFILE_IMAGE_BYTES)
    return task_response(await uc.set_image(actor, project_id, route_id, png, remember=remember))


@router.put(_TASK + "/plate", response_model=s.SigningTask)
async def set_signing_task_plate(
    project_id: UUID, route_id: UUID, body: s.SetSigningTaskPlateRequest, uc: FromDishka[SigningTaskScenario]
) -> s.SigningTask:
    """Данные плашки из своего ключа Студии."""
    actor = reader()
    identity_id = key_id(body.identity_id)
    assert identity_id is not None  # noqa: S101 — поле обязательное, None не приходит
    return task_response(await uc.set_plate_key(actor, project_id, route_id, identity_id))


@router.post(_TASK + "/plate/file", response_model=s.SigningTask)
async def upload_signing_task_plate(
    project_id: UUID, route_id: UUID, uc: FromDishka[SigningTaskScenario], file: UploadFile = File(...)
) -> s.SigningTask:
    """Данные плашки из сертификата X.509 или открытого ключа OpenPGP файлом."""
    actor = reader()
    blob = await _upload(file, MAX_PROFILE_KEY_BYTES)
    return task_response(await uc.set_plate_file(actor, project_id, route_id, blob))
