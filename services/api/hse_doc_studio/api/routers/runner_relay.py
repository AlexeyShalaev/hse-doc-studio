"""Ретрансляция ИИ в протоколе раннера: тело запроса к модели и порции ответа (`/api/runner/v1/jobs/{id}/relay`)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.runner_auth import JOB_TOKEN_HEADER, authenticated_runner
from hse_doc_studio.api.schemas.runner import RelayEventAckBody, RelayEventBatchBody
from hse_doc_studio.core.jobs.relay import RelayEventKind
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.core.jobs.wire import RUNNER_API_PREFIX, RelayEvent, RelayEventBatch
from hse_doc_studio.use_cases.ai_relay.runner_side import RelayRunnerService

RELAY_SHA256_HEADER = "X-Relay-Sha256"

router = APIRouter(prefix=RUNNER_API_PREFIX, tags=["runner"], dependencies=[Depends(require_server_mode)])


async def _service(request: Request) -> RelayRunnerService:
    return await request.state.dishka_container.get(RelayRunnerService)


@router.get("/jobs/{job_id}/relay/request")
async def get_relay_request(
    job_id: UUID,
    request: Request,
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> Response:
    """Тело запроса к модели; раннер сверяет хеш из заголовка и размер из нагрузки."""
    stored = await (await _service(request)).request_body(runner, job_id, job_token)
    return Response(
        content=stored.body, media_type="application/octet-stream", headers={RELAY_SHA256_HEADER: stored.sha256}
    )


@router.post("/jobs/{job_id}/relay/events", response_model=RelayEventAckBody)
async def post_relay_events(
    job_id: UUID,
    body: RelayEventBatchBody,
    request: Request,
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> RelayEventAckBody:
    """Порция событий по порядку; ответ ждёт места в буфере канала (обратное давление) и несёт `cancel`."""
    batch = RelayEventBatch(
        attempt=body.attempt,
        seq=body.seq,
        events=tuple(
            RelayEvent(
                kind=RelayEventKind(event.kind),
                status=event.status,
                content_type=event.content_type,
                data=event.data,
                code=event.code,
            )
            for event in body.events
        ),
    )
    ack = await (await _service(request)).push_events(runner, job_id, job_token, batch)
    return RelayEventAckBody(cancel=ack.cancel)
