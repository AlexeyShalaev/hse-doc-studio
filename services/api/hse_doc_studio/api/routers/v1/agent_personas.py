from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, status

from hse_doc_studio.api.schemas.agent_personas import (
    AgentPersonaResponse,
    BuiltinPersonaResponse,
    CreateAgentPersonaRequest,
    UpdateAgentPersonaRequest,
)
from hse_doc_studio.core.entities import AgentPersona
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.agent_personas.create_agent_persona import (
    CreateAgentPersonaInput,
    CreateAgentPersonaUC,
)
from hse_doc_studio.use_cases.agent_personas.delete_agent_persona import (
    DeleteAgentPersonaInput,
    DeleteAgentPersonaUC,
)
from hse_doc_studio.use_cases.agent_personas.get_agent_persona import (
    GetAgentPersonaInput,
    GetAgentPersonaUC,
)
from hse_doc_studio.use_cases.agent_personas.list_agent_personas import ListAgentPersonasUC
from hse_doc_studio.use_cases.agent_personas.update_agent_persona import (
    UpdateAgentPersonaInput,
    UpdateAgentPersonaUC,
)
from hse_doc_studio.use_cases.chat.personas import builtin_duplicable_personas

router = APIRouter(route_class=DishkaRoute)


def _map_persona(persona: AgentPersona) -> AgentPersonaResponse:
    return AgentPersonaResponse(
        id=persona.id,
        label=persona.label,
        description=persona.description,
        instruction=persona.instruction,
        created_at=persona.created_at,
    )


@router.get("/agent-personas", response_model=list[AgentPersonaResponse])
async def list_agent_personas(uc: FromDishka[ListAgentPersonasUC]) -> list[AgentPersonaResponse]:
    result = await uc.execute()
    return [_map_persona(p) for p in result.personas]


@router.get("/agent-personas/builtins", response_model=list[BuiltinPersonaResponse])
async def list_builtin_personas() -> list[BuiltinPersonaResponse]:
    # Shipped presets (read-only) — for the Settings UI to display and duplicate.
    # Labels/descriptions/instructions follow the interface language.
    return [
        BuiltinPersonaResponse(id=p.id, label=p.label, description=p.description, instruction=p.instruction)
        for p in builtin_duplicable_personas(current_interface_language())
    ]


@router.post("/agent-personas", response_model=AgentPersonaResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_persona(
    body: CreateAgentPersonaRequest,
    uc: FromDishka[CreateAgentPersonaUC],
) -> AgentPersonaResponse:
    try:
        result = await uc.execute(
            CreateAgentPersonaInput(label=body.label, instruction=body.instruction, description=body.description)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_persona(result.persona)


@router.get("/agent-personas/{persona_id}", response_model=AgentPersonaResponse)
async def get_agent_persona(
    persona_id: UUID,
    uc: FromDishka[GetAgentPersonaUC],
) -> AgentPersonaResponse:
    try:
        result = await uc.execute(GetAgentPersonaInput(persona_id=persona_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_persona(result.persona)


@router.patch("/agent-personas/{persona_id}", response_model=AgentPersonaResponse)
async def update_agent_persona(
    persona_id: UUID,
    body: UpdateAgentPersonaRequest,
    uc: FromDishka[UpdateAgentPersonaUC],
) -> AgentPersonaResponse:
    try:
        result = await uc.execute(
            UpdateAgentPersonaInput(
                persona_id=persona_id,
                label=body.label,
                description=body.description,
                instruction=body.instruction,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_persona(result.persona)


@router.delete("/agent-personas/{persona_id}", status_code=204)
async def delete_agent_persona(
    persona_id: UUID,
    uc: FromDishka[DeleteAgentPersonaUC],
) -> None:
    try:
        await uc.execute(DeleteAgentPersonaInput(persona_id=persona_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
