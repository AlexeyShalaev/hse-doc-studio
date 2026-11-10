"""Маршрут подписания «Отправить на подписание» через MCP (docs/design/signing-route.md, раздел 6.8).

Три тула, только на сервере (локальная Студия маршрутов не ведёт, раздел 6.9):

- `get_signing_route`: ход маршрута точки сдачи (шаги, кто ждёт, причина остановки) теми же сценариями и с тем же
  правом `OUTPUT_READ`, что `GET .../signing-routes`;
- `list_signing_tasks`: задачи владельца токена «На подпись» по всем проектам, как `GET /account/signing-tasks`;
- `send_for_signing`: отправить маршрут точки, как кнопка «Отправить на подписание»: тот же предпросмотр, те же
  помехи и отпечатки документов, что у `POST .../send`. Опасный: по умолчанию выключен (docs/design/mcp.md, M6).

Согласовать, подписать и вернуть на доработку через MCP нельзя: это решение человека на странице подписи. Ключ
подписи в отправку не передаётся («Отправить и подписать» остаётся в интерфейсе), приглашённого без аккаунта тул не
ждёт: маршрут уходит, только когда все его участники уже в проекте.
"""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.core.signing_route.entities import SENDABLE_STATUSES, RouteConflictError, RouteStatus
from hse_doc_studio.core.signing_route.readiness import Blocker, BlockerCode, RouteBlockedError
from hse_doc_studio.use_cases.mcp.tools._base import McpTool, json_result, optional_text, project_schema, text_arg
from hse_doc_studio.use_cases.signing_route.author import (
    RoutePreview,
    RouteSummary,
    SendRequest,
    SigningRouteDrafts,
    SigningRouteSending,
)
from hse_doc_studio.use_cases.signing_route.reminders import signing_page_path
from hse_doc_studio.use_cases.signing_route.tasks import ListSigningTasksUC
from hse_doc_studio.use_cases.signing_route.views import EventView, Membership, PersonView, RouteDetails

# Сколько последних событий истории маршрута отдавать модели.
_EVENTS = 30

_PROFILE_ARG = {"type": "string", "description": "Точка сдачи: id профиля из list_submission_profiles"}


def _member(actor: Actor) -> Actor:
    """Вошедший человек: гостю и открывшему проект по ссылке маршрут не раскрывается (раздел 7)."""
    if actor.id is None or actor.is_guest or actor.link_id is not None:
        raise McpError(McpErrorCode.not_found)
    return actor


def _page(project_id: UUID, route_id: UUID) -> str:
    return signing_page_path(project_id, route_id)


def _person(person: PersonView, *, round: int) -> dict[str, object]:
    p = person.participant
    approval = p.approval if p.approval is not None and p.approval.round == round else None
    return {
        "participant_id": str(p.id),
        "name": person.name,
        "persona": p.persona,
        "membership": person.membership.value,
        "method": person.method.value if person.method is not None else None,
        "state": person.view.state.value,
        "next_action": person.view.next_action.value,
        "approved_at": approval.at if approval is not None else None,
        "reminded_at": p.reminded_at,
        "slots": [{"doc_id": pair.doc_id, "slot_id": pair.slot_id} for pair in p.assignments],
    }


def _waiting(person: PersonView) -> dict[str, object]:
    return {
        "name": person.name,
        "persona": person.participant.persona,
        "step": person.step,
        "state": person.view.state.value,
        "next_action": person.view.next_action.value,
    }


def _event(view: EventView) -> dict[str, object]:
    event = view.event
    return {
        "kind": event.kind.value,
        "round": event.round,
        "at": event.at,
        "who": view.who,
        "participant_id": str(event.participant_id) if event.participant_id is not None else None,
        "reason": view.reason.value if view.reason is not None else None,
        "comment": view.comment,
    }


def route_view(details: RouteDetails) -> dict[str, object]:
    """Ход маршрута для модели: статус, шаги с людьми и их состояниями, кто ждёт и почему маршрут остановлен."""
    route = details.route
    stopped = next((p for p in details.people if p.participant.id == route.stopped_by), None)
    return {
        "route_id": str(route.id),
        "profile": {"id": route.profile_id, "name": details.profile_name},
        "status": details.status.value,
        "phase": details.phase.value if details.phase is not None else None,
        "round": route.round,
        "current_step": details.current_step,
        "steps_total": len(details.steps),
        "deadline": route.deadline,
        "message": route.message,
        "stop_reason": details.stop_reason.value if details.stop_reason is not None else None,
        "stopped_by": {"name": stopped.name, "persona": stopped.participant.persona} if stopped is not None else None,
        "sent_by": details.sent_by_name,
        "sent_at": route.sent_at,
        "completed_at": route.completed_at,
        "waiting_for": [_waiting(person) for person in details.waiting_for],
        "steps": [[_person(person, round=route.round) for person in step] for step in details.steps],
        "docs": [
            {
                "doc_id": doc.doc_id,
                "name": doc.name,
                "built": doc.built,
                "frozen": doc.frozen,
                "slots": [
                    {
                        "slot_id": slot.slot_id,
                        "label": slot.label,
                        "optional": slot.optional,
                        "status": slot.status.value,
                        "reason": slot.reason.value if slot.reason is not None else None,
                    }
                    for slot in doc.slots
                ],
            }
            for doc in details.docs
        ],
        "events": [_event(e) for e in details.events[-_EVENTS:]],
        "signing_page": _page(route.project_id, route.id),
    }


def _summary(item: RouteSummary) -> dict[str, object]:
    route = item.route
    return {
        "route_id": str(route.id),
        "profile": {"id": route.profile_id, "name": item.profile_name},
        "status": item.status.value,
        "phase": item.phase.value if item.phase is not None else None,
        "round": route.round,
        "current_step": item.current_step,
        "steps_total": item.steps_total,
        "deadline": route.deadline,
        "stop_reason": item.stop_reason.value if item.stop_reason is not None else None,
        "sent_at": route.sent_at,
        "completed_at": route.completed_at,
        "waiting_for": [{"name": name, "persona": persona} for name, persona in item.waiting_for],
    }


class GetSigningRouteTool(McpTool):
    spec = ToolSpec(
        name="get_signing_route",
        description=(
            "Ход маршрута подписания точки сдачи («Отправить на подписание»): статус и фаза, шаги с людьми и их "
            "состояниями, чья очередь сейчас, срок, причина остановки (документ изменился, вернули на доработку, "
            "участник ушёл) и последние события. Без profile_id сводка по всем маршрутам проекта. Только чтение: "
            "согласовать, подписать или вернуть на доработку можно только на странице подписи в интерфейсе."
        ),
        parameters=project_schema({"profile_id": _PROFILE_ARG}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        actor = _member(require_actor())
        drafts = await self._deps.get(SigningRouteDrafts)
        profile_id = optional_text(args, "profile_id")
        summaries = await drafts.list_routes(ctx.project_id, profile_id)
        if profile_id is None:
            return json_result({"routes": [_summary(item) for item in summaries]})
        # Маршруты точки идут от новых к старым: текущий это первый, который не снят с контроля.
        current = next((item for item in summaries if item.route.status is not RouteStatus.archived), None)
        if current is None:
            return json_result(
                {
                    "route": None,
                    "hint": localized_error(
                        "У точки сдачи нет маршрута подписания: его отправляет автор кнопкой «Отправить на "
                        "подписание» или тулом send_for_signing",
                        "The checkpoint has no signing route: the author sends one with “Send for signing” or "
                        "the send_for_signing tool",
                    ),
                }
            )
        return json_result({"route": route_view(await drafts.get(actor, ctx.project_id, current.route.id))})


class ListSigningTasksTool(McpTool):
    spec = ToolSpec(
        name="list_signing_tasks",
        description=(
            "Мои задачи «На подпись» по всем проектам: маршруты, где сейчас нужно моё действие (согласовать, "
            "согласовать и подписать, подписать итоговый PDF), с проектом, точкой сдачи, отправителем и сроком. "
            "Само действие выполняется только на странице подписи в интерфейсе (поле signing_page)."
        ),
        parameters={"type": "object", "properties": {}},
    )
    kind = ToolKind.read
    requires_project = False

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        actor = _member(require_actor())
        tasks = await (await self._deps.get(ListSigningTasksUC)).execute(actor.id or "")
        return json_result(
            {
                "tasks": [
                    {
                        "project": {"id": str(task.project_id), "name": task.project_name},
                        "route_id": str(task.route_id),
                        "profile": {"id": task.profile_id, "name": dict(task.profile_name)},
                        "round": task.round,
                        "sender": task.sender,
                        "deadline": task.deadline,
                        "next_action": task.next_action.value,
                        "since": task.since,
                        "signing_page": _page(task.project_id, task.route_id),
                    }
                    for task in tasks
                ]
            }
        )


def _blocker_text(blocker: Blocker, preview: RoutePreview) -> str:
    """Помеха отправки словами: что не готово и чем это исправить."""
    doc, slot = blocker.doc_id or "", blocker.slot_id or ""
    personas = {p.participant.id: p.participant.persona for p in preview.participants}
    persona = personas.get(blocker.participant_id, "") if blocker.participant_id is not None else ""
    texts = {
        BlockerCode.not_built: localized_error(
            f"документ {doc} не собран: соберите его (compile_document)",
            f"document {doc} is not built: build it (compile_document)",
        ),
        BlockerCode.participant_missing: localized_error(
            f"в проекте нет человека с персоной {persona}: пригласите его (invite_to_project с persona) или "
            "выберите другого в интерфейсе",
            f"nobody in the project has the {persona} persona: invite them (invite_to_project with persona) or "
            "pick someone else in the interface",
        ),
        BlockerCode.slot_unassigned: localized_error(
            f"у слота {slot} документа {doc} нет участника маршрута: добавьте его в интерфейсе",
            f"slot {slot} of document {doc} has no route participant: add one in the interface",
        ),
        BlockerCode.sender_not_ready: localized_error(
            "ваша подпись не готова: загрузите картинку подписи или укажите ключ для плашки в интерфейсе",
            "your signature is not ready: upload a signature image or set the plate key in the interface",
        ),
        BlockerCode.doc_in_other_route: localized_error(
            f"документ {doc} уже на подписании по другому маршруту",
            f"document {doc} is already on another signing route",
        ),
        BlockerCode.placement_off: localized_error(
            f"у слота {slot} документа {doc} не включено место на странице: включите размещение в интерфейсе",
            f"slot {slot} of document {doc} has no place on the page: turn its placement on in the interface",
        ),
        BlockerCode.no_participants: localized_error("в маршруте нет участников", "the route has no participants"),
    }
    return texts[blocker.code]


def _invited_text(preview: RoutePreview) -> list[str]:
    """Участники, которые ещё не приняли приглашение: через MCP маршрут с ними не уходит (раздел 6.8)."""
    return [
        localized_error(
            f"{p.name or p.participant.persona} ({p.participant.persona}) ещё не принял приглашение в проект: "
            "дождитесь принятия или отправьте маршрут из интерфейса",
            f"{p.name or p.participant.persona} ({p.participant.persona}) has not accepted the project invitation "
            "yet: wait for it or send the route from the interface",
        )
        for p in preview.participants
        if p.membership is Membership.invited
    ]


def _refusal(reasons: list[str]) -> ToolResult:
    head = localized_error("Маршрут не отправлен:", "The route was not sent:")
    return ToolResult.error("\n".join([head, *(f"- {reason}" for reason in reasons)]))


class SendForSigningTool(McpTool):
    spec = ToolSpec(
        name="send_for_signing",
        description=(
            "Отправить документы точки сдачи на подписание по маршруту, как кнопка «Отправить на подписание»: "
            "подписанты получат уведомления и письма по порядку шагов. Берёт сохранённый маршрут точки (черновик, "
            "остановленный или возвращённый на доработку: тогда это «Отправить заново»), а если его нет, создаёт "
            "из прежнего маршрута или порядка пака. Отправляет, только если ничего не мешает: документы собраны, "
            "все участники уже в проекте, подпись отправителя готова; иначе отвечает списком помех и ничего не "
            "отправляет. Если отправитель участник первого шага, отправка считается его согласованием. Ключом "
            "не подписывает и за других не согласует: это делается на странице подписи в интерфейсе."
        ),
        parameters=project_schema({"profile_id": _PROFILE_ARG}, required=("profile_id",)),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        actor = _member(require_actor())
        profile_id = text_arg(args, "profile_id")
        try:
            return await self._send(actor, ctx.project_id, profile_id)
        except RouteBlockedError as exc:
            # Помеха появилась между предпросмотром и отправкой.
            return _refusal([b.code.value for b in exc.blockers])
        except RouteConflictError as exc:
            raise McpError(McpErrorCode.failed, str(exc)) from exc
        except IdentityError as exc:
            if exc.code is not IdentityErrorCode.rate_limited:
                raise
            raise McpError(
                McpErrorCode.rate_limited,
                localized_error(
                    "Маршрут отправляли меньше минуты назад, повторите позже",
                    "The route was sent less than a minute ago, try again later",
                ),
                retry_after_s=exc.retry_after_s,
            ) from exc
        except NotFoundError as exc:
            # Проект и право на него уже проверены вызовом тула: не найдена точка сдачи.
            raise McpError(McpErrorCode.not_found, str(exc) or None) from exc

    async def _send(self, actor: Actor, project_id: UUID, profile_id: str) -> ToolResult:
        drafts = await self._deps.get(SigningRouteDrafts)
        sending = await self._deps.get(SigningRouteSending)
        details, _ = await drafts.create(actor, project_id, profile_id)
        route = details.route
        if route.status not in SENDABLE_STATUSES:
            return _refusal(
                [
                    localized_error(
                        "маршрут точки уже отправлен и идёт: его ход показывает get_signing_route, отменить "
                        "его можно в интерфейсе",
                        "the checkpoint route is already sent and running: get_signing_route shows its "
                        "progress, it can be cancelled in the interface",
                    )
                ]
            )
        preview = await sending.preview(actor, project_id, route.id)
        reasons = [*(_blocker_text(b, preview) for b in preview.blockers), *_invited_text(preview)]
        if reasons:
            return _refusal(reasons)
        # Уходит ровно то, что показал этот предпросмотр: пересборка между ним и отправкой даёт отказ.
        expected = {doc_id: token for doc_id, _name, _built, token in preview.docs if token is not None}
        sent = await sending.send(actor, project_id, route.id, SendRequest(expected=expected))
        return json_result({"sent": True, "route": route_view(sent)})
