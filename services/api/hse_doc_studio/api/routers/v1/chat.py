from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from hse_doc_studio.api.schemas.chat import (
    AgentToolResponse,
    AnswerTurnRequest,
    ApproveTurnRequest,
    CancelTurnResponse,
    ChatContentBlockResponse,
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    CreateChatSessionRequest,
    PersonaResponse,
    RenameChatSessionRequest,
    StartTurnRequest,
    StartTurnResponse,
    TokenUsageResponse,
)
from hse_doc_studio.core.agent.entities import AgentEvent, TokenUsage
from hse_doc_studio.core.entities import ChatContentBlock, ChatMessage, ChatSession
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.agent_personas.list_selectable_personas import ListSelectablePersonasUC
from hse_doc_studio.use_cases.chat.cancel_chat_turn import CancelChatTurnInput, CancelChatTurnUC
from hse_doc_studio.use_cases.chat.create_chat_session import (
    CreateChatSessionInput,
    CreateChatSessionUC,
)
from hse_doc_studio.use_cases.chat.delete_chat_session import (
    DeleteChatSessionInput,
    DeleteChatSessionUC,
)
from hse_doc_studio.use_cases.chat.get_chat_run_stream import (
    GetChatRunStreamInput,
    GetChatRunStreamUC,
)
from hse_doc_studio.use_cases.chat.get_chat_session import GetChatSessionInput, GetChatSessionUC
from hse_doc_studio.use_cases.chat.list_agent_tools import ListAgentToolsUC
from hse_doc_studio.use_cases.chat.list_chat_sessions import ListChatSessionsInput, ListChatSessionsUC
from hse_doc_studio.use_cases.chat.rename_chat_session import (
    RenameChatSessionInput,
    RenameChatSessionUC,
)
from hse_doc_studio.use_cases.chat.start_chat_turn import StartChatTurnInput, StartChatTurnUC
from hse_doc_studio.use_cases.chat.system_chat import (
    SystemCancelChatTurnUC,
    SystemCreateChatSessionUC,
    SystemDeleteChatSessionUC,
    SystemGetChatSessionUC,
    SystemListChatSessionsUC,
    SystemRenameChatSessionUC,
)
from hse_doc_studio.use_cases.chat.system_get_chat_run_stream import SystemGetChatRunStreamUC
from hse_doc_studio.use_cases.chat.system_start_chat_turn import (
    SystemStartChatTurnInput,
    SystemStartChatTurnUC,
)

router = APIRouter(route_class=DishkaRoute)
logger = structlog.get_logger()


def _sse(stream: AsyncIterator[AgentEvent]) -> StreamingResponse:
    async def _event_stream() -> AsyncIterator[str]:
        async for event in stream:
            yield f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _map_usage(usage: TokenUsage | None) -> TokenUsageResponse | None:
    if usage is None:
        return None
    return TokenUsageResponse(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )


def _map_block(block: ChatContentBlock) -> ChatContentBlockResponse:
    return ChatContentBlockResponse(
        kind=str(block.kind),
        text=block.text,
        call_id=block.call_id,
        tool_name=block.tool_name,
        args=block.args,
        result=block.result,
        is_error=block.is_error,
    )


def _map_message(message: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        seq=message.seq,
        role=str(message.role),
        blocks=[_map_block(b) for b in message.blocks],
        created_at=message.created_at,
        model=message.model,
        provider_id=message.provider_id,
        usage=_map_usage(message.usage),
        approval=str(message.approval),
    )


def _map_session(session: ChatSession, *, is_running: bool = False) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        doc_id=session.doc_id,
        project_id=session.project_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        archived=session.archived,
        message_count=session.message_count,
        last_run_id=session.last_run_id,
        default_provider_id=session.default_provider_id,
        default_model=session.default_model,
        persona=session.persona,
        persona_instructions=session.persona_instructions,
        is_running=is_running,
    )


@router.get("/agent/tools", response_model=list[AgentToolResponse])
async def list_agent_tools(uc: FromDishka[ListAgentToolsUC]) -> list[AgentToolResponse]:
    result = await uc.execute()
    return [
        AgentToolResponse(
            name=t.name,
            description=t.description,
            kind=t.kind,
            requires_project=t.requires_project,
        )
        for t in result.tools
    ]


@router.get("/agent/personas", response_model=list[PersonaResponse])
async def list_agent_personas(uc: FromDishka[ListSelectablePersonasUC]) -> list[PersonaResponse]:
    # Global, project-independent: built-in presets + user-defined custom roles.
    result = await uc.execute()
    return [
        PersonaResponse(id=p.id, label=p.label, description=p.description, builtin=p.builtin) for p in result.personas
    ]


@router.get("/projects/{project_id}/chats", response_model=list[ChatSessionResponse])
async def list_chats(project_id: UUID, uc: FromDishka[ListChatSessionsUC]) -> list[ChatSessionResponse]:
    try:
        result = await uc.execute(ListChatSessionsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_map_session(s, is_running=s.id in result.active_session_ids) for s in result.sessions]


@router.post("/projects/{project_id}/chats", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    project_id: UUID,
    body: CreateChatSessionRequest,
    uc: FromDishka[CreateChatSessionUC],
) -> ChatSessionResponse:
    try:
        result = await uc.execute(
            CreateChatSessionInput(
                project_id=project_id,
                title=body.title,
                doc_id=body.doc_id,
                default_provider_id=body.provider_id,
                default_model=body.model,
                persona=body.persona,
                persona_instructions=body.persona_instructions,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_session(result.session)


@router.get("/projects/{project_id}/chats/{session_id}", response_model=ChatSessionDetailResponse)
async def get_chat(
    project_id: UUID,
    session_id: UUID,
    uc: FromDishka[GetChatSessionUC],
) -> ChatSessionDetailResponse:
    try:
        result = await uc.execute(GetChatSessionInput(project_id=project_id, session_id=session_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    base = _map_session(result.session)
    return ChatSessionDetailResponse(
        **base.model_dump(),
        messages=[_map_message(m) for m in result.messages],
        active_run_id=result.active_run_id,
    )


@router.patch("/projects/{project_id}/chats/{session_id}", response_model=ChatSessionResponse)
async def rename_chat(
    project_id: UUID,
    session_id: UUID,
    body: RenameChatSessionRequest,
    uc: FromDishka[RenameChatSessionUC],
) -> ChatSessionResponse:
    try:
        result = await uc.execute(
            RenameChatSessionInput(
                project_id=project_id,
                session_id=session_id,
                title=body.title,
                persona=body.persona,
                persona_instructions=body.persona_instructions,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_session(result.session)


@router.delete("/projects/{project_id}/chats/{session_id}", status_code=204)
async def delete_chat(
    project_id: UUID,
    session_id: UUID,
    uc: FromDishka[DeleteChatSessionUC],
) -> None:
    try:
        await uc.execute(DeleteChatSessionInput(project_id=project_id, session_id=session_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/chats/{session_id}/turns",
    response_model=StartTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_turn(
    project_id: UUID,
    session_id: UUID,
    body: StartTurnRequest,
    uc: FromDishka[StartChatTurnUC],
) -> StartTurnResponse:
    try:
        result = await uc.execute(
            StartChatTurnInput(
                project_id=project_id,
                session_id=session_id,
                text=body.text,
                provider_id=body.provider_id,
                model=body.model,
            )
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartTurnResponse(run_id=result.run_id, user_message_seq=result.user_message_seq)


@router.get("/projects/{project_id}/chats/{session_id}/runs/{run_id}/stream")
async def stream_run(
    project_id: UUID,
    session_id: UUID,
    run_id: UUID,
    uc: FromDishka[GetChatRunStreamUC],
) -> StreamingResponse:
    stream = await uc.execute(GetChatRunStreamInput(project_id=project_id, session_id=session_id, run_id=run_id))
    return _sse(stream)


@router.post(
    "/projects/{project_id}/chats/{session_id}/runs/{run_id}/approve",
    response_model=StartTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_turn(
    project_id: UUID,
    session_id: UUID,
    run_id: UUID,
    body: ApproveTurnRequest,
    uc: FromDishka[StartChatTurnUC],
) -> StartTurnResponse:
    try:
        result = await uc.execute(
            StartChatTurnInput(
                project_id=project_id,
                session_id=session_id,
                run_id=run_id,
                approved_call_ids=tuple(body.call_ids),
            )
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartTurnResponse(run_id=result.run_id, user_message_seq=result.user_message_seq)


@router.post(
    "/projects/{project_id}/chats/{session_id}/runs/{run_id}/answer",
    response_model=StartTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def answer_turn(
    project_id: UUID,
    session_id: UUID,
    run_id: UUID,
    body: AnswerTurnRequest,
    uc: FromDishka[StartChatTurnUC],
) -> StartTurnResponse:
    try:
        result = await uc.execute(
            StartChatTurnInput(
                project_id=project_id,
                session_id=session_id,
                run_id=run_id,
                tool_answers=body.answers,
            )
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartTurnResponse(run_id=result.run_id, user_message_seq=result.user_message_seq)


@router.post(
    "/projects/{project_id}/chats/{session_id}/runs/{run_id}/cancel",
    response_model=CancelTurnResponse,
)
async def cancel_run(
    project_id: UUID,
    session_id: UUID,
    run_id: UUID,
    uc: FromDishka[CancelChatTurnUC],
) -> CancelTurnResponse:
    try:
        result = await uc.execute(CancelChatTurnInput(project_id=project_id, session_id=session_id, run_id=run_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CancelTurnResponse(
        cancelled_task=result.cancelled_task,
        record_finalized=result.record_finalized,
    )


# ----------------------------------------------------------------------- System (no-project) agent
# A global assistant whose chats live in an app-level folder (not a project).
# Reuses the chat stack + the mappers above; only the scope (no project_id) differs.


@router.get("/agent/chats", response_model=list[ChatSessionResponse])
async def list_system_chats(uc: FromDishka[SystemListChatSessionsUC]) -> list[ChatSessionResponse]:
    result = await uc.execute()
    return [_map_session(s, is_running=s.id in result.active_session_ids) for s in result.sessions]


@router.post("/agent/chats", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_system_chat(
    body: CreateChatSessionRequest,
    uc: FromDishka[SystemCreateChatSessionUC],
) -> ChatSessionResponse:
    result = await uc.execute(
        title=body.title,
        default_provider_id=body.provider_id,
        default_model=body.model,
        project_id=body.project_id,
        persona=body.persona,
        persona_instructions=body.persona_instructions,
    )
    return _map_session(result.session)


@router.get("/agent/chats/{session_id}", response_model=ChatSessionDetailResponse)
async def get_system_chat(
    session_id: UUID,
    uc: FromDishka[SystemGetChatSessionUC],
) -> ChatSessionDetailResponse:
    try:
        result = await uc.execute(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    base = _map_session(result.session)
    return ChatSessionDetailResponse(
        **base.model_dump(),
        messages=[_map_message(m) for m in result.messages],
        active_run_id=result.active_run_id,
    )


@router.patch("/agent/chats/{session_id}", response_model=ChatSessionResponse)
async def rename_system_chat(
    session_id: UUID,
    body: RenameChatSessionRequest,
    uc: FromDishka[SystemRenameChatSessionUC],
) -> ChatSessionResponse:
    try:
        result = await uc.execute(
            session_id,
            title=body.title,
            persona=body.persona,
            persona_instructions=body.persona_instructions,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_session(result.session)


@router.delete("/agent/chats/{session_id}", status_code=204)
async def delete_system_chat(
    session_id: UUID,
    uc: FromDishka[SystemDeleteChatSessionUC],
) -> None:
    try:
        await uc.execute(session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/agent/chats/{session_id}/turns",
    response_model=StartTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_system_turn(
    session_id: UUID,
    body: StartTurnRequest,
    uc: FromDishka[SystemStartChatTurnUC],
) -> StartTurnResponse:
    try:
        result = await uc.execute(
            SystemStartChatTurnInput(
                session_id=session_id,
                text=body.text,
                provider_id=body.provider_id,
                model=body.model,
            )
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartTurnResponse(run_id=result.run_id, user_message_seq=result.user_message_seq)


@router.post(
    "/agent/chats/{session_id}/runs/{run_id}/approve",
    response_model=StartTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_system_turn(
    session_id: UUID,
    run_id: UUID,
    body: ApproveTurnRequest,
    uc: FromDishka[SystemStartChatTurnUC],
) -> StartTurnResponse:
    try:
        result = await uc.execute(
            SystemStartChatTurnInput(session_id=session_id, run_id=run_id, approved_call_ids=tuple(body.call_ids))
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartTurnResponse(run_id=result.run_id, user_message_seq=result.user_message_seq)


@router.post(
    "/agent/chats/{session_id}/runs/{run_id}/answer",
    response_model=StartTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def answer_system_turn(
    session_id: UUID,
    run_id: UUID,
    body: AnswerTurnRequest,
    uc: FromDishka[SystemStartChatTurnUC],
) -> StartTurnResponse:
    try:
        result = await uc.execute(
            SystemStartChatTurnInput(session_id=session_id, run_id=run_id, tool_answers=body.answers)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartTurnResponse(run_id=result.run_id, user_message_seq=result.user_message_seq)


@router.post("/agent/chats/{session_id}/runs/{run_id}/cancel", response_model=CancelTurnResponse)
async def cancel_system_run(
    session_id: UUID,
    run_id: UUID,
    uc: FromDishka[SystemCancelChatTurnUC],
) -> CancelTurnResponse:
    try:
        result = await uc.execute(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CancelTurnResponse(cancelled_task=result.cancelled_task, record_finalized=result.record_finalized)


@router.get("/agent/chats/{session_id}/runs/{run_id}/stream")
async def stream_system_run(
    session_id: UUID,
    run_id: UUID,
    uc: FromDishka[SystemGetChatRunStreamUC],
) -> StreamingResponse:
    stream = await uc.execute(session_id, run_id)
    return _sse(stream)
