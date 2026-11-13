"""Маршрут подписания «Отправить на подписание» через MCP (docs/design/signing-route.md, раздел 6.8).

Три тула, только на сервере (локальная Студия маршрутов не ведёт, раздел 6.9):

- `get_signing_route`: ход маршрута точки сдачи (шаги, кто ждёт, причина остановки) теми же сценариями и с тем же
  правом `OUTPUT_READ`, что `GET .../signing-routes`;
- `list_signing_tasks`: задачи владельца токена «На подпись» по всем проектам, как `GET /account/signing-tasks`;
- `send_for_signing`: отправить маршрут точки, как кнопка «Отправить на подписание»: тот же предпросмотр, те же
  помехи и отпечатки документов, что у `POST .../send`. Опасный: по умолчанию выключен (docs/design/mcp.md, M6).

Маршрут подписывает версию на подписи, снятую при отправке (раздел 12): `get_signing_route` показывает её у каждого
документа (`sent`) и изменения после отправки (`changed`, `changed_docs`). Новую версию идущего или завершённого
маршрута `send_for_signing` не отправляет (отказ `new_version_in_ui`, 12.10): она сбрасывает чужие согласия.

Согласовать, подписать и вернуть на доработку через MCP нельзя: это решение человека на странице подписи. Ключ
подписи в отправку не передаётся («Отправить и подписать» остаётся в интерфейсе), приглашённого без аккаунта тул не
ждёт: маршрут уходит, только когда все его участники уже в проекте.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.catalog import SlotCondition
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.core.signing_route.entities import (
    EDITABLE_STATUSES,
    NEW_VERSION_STATUSES,
    ParticipantState,
    RouteConflictError,
    RouteStatus,
    StopReason,
)
from hse_doc_studio.core.signing_route.preset import PresetDiff
from hse_doc_studio.core.signing_route.readiness import Blocker, BlockerCode, OtherRoute, RouteBlockedError
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
from hse_doc_studio.use_cases.signing_route.views import DocView, EventView, Membership, PersonView, RouteDetails

# Сколько последних событий истории маршрута отдавать модели.
_EVENTS = 30

_PROFILE_ARG = {"type": "string", "description": "Контрольная точка: id профиля из list_submission_profiles"}


def _member(actor: Actor) -> Actor:
    """Вошедший человек: гостю и открывшему проект по ссылке маршрут не раскрывается (раздел 7)."""
    if actor.id is None or actor.is_guest or actor.link_id is not None:
        raise McpError(McpErrorCode.not_found)
    return actor


def _page(project_id: UUID, route_id: UUID) -> str:
    return signing_page_path(project_id, route_id)


def _person(person: PersonView) -> dict[str, object]:
    p = person.participant
    # Согласие переносится в новый раунд всегда (12.6); согласовавшим он считается, пока оно действует.
    approval = p.approval if person.view.approved else None
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
        # Пропуск (13.10): когда пропущен и можно ли пропустить сейчас; пропустить может только автор в интерфейсе.
        "skipped_at": p.skipped.at if person.view.state is ParticipantState.skipped and p.skipped is not None else None,
        "skippable": person.view.skip.available,
    }


def _skip_hint(details: RouteDetails) -> str | None:
    """Подсказка, когда очередь у человека, которого можно пропустить (13.10); пропуск через MCP невозможен."""
    if details.status is not RouteStatus.active:
        return None
    names = [person.name or person.participant.persona for person in details.people if person.view.skip.available]
    if not names:
        return None
    who = ", ".join(names)
    return localized_error(
        f"Все подписи ({who}) на точке необязательны. Пропустить может автор маршрута в интерфейсе",
        f"All signatures of {who} at this checkpoint are optional. The route author can skip them in the interface",
    )


def _condition(when: SlotCondition | None) -> dict[str, object] | None:
    if when is None:
        return None
    return {"person": when.person, "role": when.role.value if when.role is not None else None}


def _preset(details: RouteDetails) -> dict[str, object] | None:
    """Пресет точки (15.12): как в API, но всегда, а не только управляющему; агенту нужно знать, отличается ли
    маршрут от шаблона. None, если версия шаблона пресета не задаёт."""
    view = details.preset
    if view is None:
        return None
    preset = view.preset
    return {
        "version": preset.version,
        "base_version": details.route.preset_version,
        "steps": [list(step) for step in preset.steps],
        "extra_slots": [
            {"doc_id": item.pair.doc_id, "slot_id": item.pair.slot_id, "when": _condition(item.when)}
            for item in preset.extra_slots
        ],
        "optional": [{"doc_id": pair.doc_id, "slot_id": pair.slot_id} for pair in preset.optional],
        "skipped_by_condition": [
            {"doc_id": item.pair.doc_id, "slot_id": item.pair.slot_id, "when": _condition(item.when)}
            for item in preset.skipped_by_condition
        ],
        "differs": [diff.value for diff in view.differs],
    }


_DIFF_TEXT = {
    PresetDiff.order: ("порядок и люди", "the order and people"),
    PresetDiff.slots: ("подписи сверх точки", "the extra signatures"),
    PresetDiff.optional: ("отметки «необязательна»", "the “optional” marks"),
}


def _preset_hint(details: RouteDetails) -> str | None:
    """Подсказка, если маршрут, который можно править, отличается от шаблона (15.12): вернуть может только автор в
    интерфейсе, у MCP правки маршрута нет."""
    view = details.preset
    if view is None or not view.differs or details.route.status not in EDITABLE_STATUSES:
        return None
    ru = ", ".join(_DIFF_TEXT[diff][0] for diff in view.differs)
    en = ", ".join(_DIFF_TEXT[diff][1] for diff in view.differs)
    return localized_error(
        f"Маршрут отличается от шаблона ({ru}). Вернуть как в шаблоне может автор в интерфейсе",
        f"The route differs from the template ({en}). The author can reset it to the template in the interface",
    )


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
        # Только у `sent` новой версии: документы, у которых сменилась версия на подписи (12.9).
        "changed_docs": list(view.changed_docs) if view.changed_docs is not None else None,
    }


def _day(at: datetime) -> str:
    """Дата версии на подписи для текста: «10.11.2026» (UTC)."""
    moment = at if at.tzinfo is not None else at.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%d.%m.%Y")


def _sent(doc: DocView) -> dict[str, object] | None:
    """Версия на подписи документа (`sent` 12.9): sha256, когда снята и каким раундом; None без неё."""
    sent = doc.sent
    if sent is None:
        return None
    return {"sha256": sent.sha256, "at": sent.at, "round": sent.round}


def _changed_hint(docs: Sequence[DocView]) -> str | None:
    """Подсказка при изменениях после отправки: что подписывают и кто отправляет новую версию (12.10)."""
    changed = [doc for doc in docs if doc.changed]
    if not changed:
        return None
    ru_items, en_items = [], []
    for doc in changed:
        day = _day(doc.sent.at) if doc.sent is not None else None
        ru_items.append(f"{doc.doc_id} (подписывают версию от {day})" if day else doc.doc_id)
        en_items.append(f"{doc.doc_id} (the version sent on {day} is being signed)" if day else doc.doc_id)
    return localized_error(
        f"Есть изменения после отправки на подпись: {', '.join(ru_items)}. Подписывают версию на подписи, а не "
        "текущую сборку. Новую версию отправляет человек в интерфейсе («Отправить новую версию» в карточке "
        "«Подписание»), send_for_signing её не отправляет",
        f"There are changes since the documents were sent for signing: {', '.join(en_items)}. The signers sign the "
        "version sent for signing, not the current build. A person sends the new version in the interface (“Send "
        "new version” on the “Signing” card); send_for_signing does not send it",
    )


def _stop_reason_text(reason: StopReason) -> str:
    """Причина остановки словами: что случилось и что делать (разделы 5.5 и 12.5)."""
    texts = {
        StopReason.rebuilt: localized_error(
            "документ пересобран после отправки (маршрут остановлен до перехода на версию на подписи): человек "
            "отправляет новую версию в интерфейсе",
            "a document was rebuilt after sending (the route stopped before versions sent for signing existed): "
            "a person sends the new version in the interface",
        ),
        StopReason.sent_changed: localized_error(
            "версия на подписи изменилась или удалена вне маршрута (git, восстановление, ручная правка) или "
            "документ убран из проекта: маршрут остановлен, человек отправляет новую версию в интерфейсе",
            "the version sent for signing changed or was removed outside the route (git, restore, a manual edit) "
            "or the document left the project: the route stopped, a person sends the new version in the interface",
        ),
        StopReason.frozen_changed: localized_error(
            "зафиксированный PDF изменён или удалён вне маршрута: маршрут остановлен",
            "the frozen PDF changed or was removed outside the route: the route stopped",
        ),
        StopReason.marks_changed: localized_error(
            "видимый слой подписей изменён вне маршрута: маршрут остановлен",
            "the visible signature layer changed outside the route: the route stopped",
        ),
        StopReason.participant_left: localized_error(
            "участник ушёл из проекта или сменил персону: замените его в интерфейсе и отправьте заново",
            "a participant left the project or changed persona: replace them in the interface and send again",
        ),
        StopReason.returned: localized_error(
            "подписант вернул на доработку: исправьте и отправьте заново",
            "a signer returned the documents for rework: fix them and send again",
        ),
    }
    return texts.get(reason, reason.value)


def _stop_text(reason: StopReason | None, docs: Sequence[DocView]) -> str | None:
    if reason is None:
        return None
    if reason is StopReason.sent_changed and any(doc.changed and doc.sent is None for doc in docs):
        # Маршрут 0.20.0, перенос которого не нашёл прежнюю сборку (12.11).
        return localized_error(
            "Версию, отправленную на подпись, восстановить нельзя: человек отправляет новую версию в интерфейсе",
            "The version sent for signing cannot be restored: a person sends the new version in the interface",
        )
    return _stop_reason_text(reason)


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
        "stop_text": _stop_text(details.stop_reason, details.docs),
        "stopped_by": {"name": stopped.name, "persona": stopped.participant.persona} if stopped is not None else None,
        "sent_by": details.sent_by_name,
        "sent_at": route.sent_at,
        "completed_at": route.completed_at,
        "waiting_for": [_waiting(person) for person in details.waiting_for],
        "steps": [[_person(person) for person in step] for step in details.steps],
        "docs": [
            {
                "doc_id": doc.doc_id,
                "name": doc.name,
                "built": doc.built,
                "frozen": doc.frozen,
                "sent": _sent(doc),
                "changed": doc.changed,
                "slots": [
                    {
                        "slot_id": slot.slot_id,
                        "label": slot.label,
                        "extra": slot.extra,
                        "optional": slot.optional,
                        "status": slot.status.value,
                        "reason": slot.reason.value if slot.reason is not None else None,
                        # Кто добавил слот сверх точки (15.12): `pack` шаблон, `author` автор; null у пары точки.
                        "added_by": slot.added_by.value if slot.added_by is not None else None,
                        "preset_optional": slot.preset_optional,
                    }
                    for slot in doc.slots
                ],
            }
            for doc in details.docs
        ],
        "changed_docs": list(details.changed_docs),
        "changed_hint": _changed_hint(details.docs),
        "skip_hint": _skip_hint(details),
        "preset": _preset(details),
        "preset_hint": _preset_hint(details),
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
        "docs": list(route.docs),
        "changed_docs": list(item.changed_docs),
    }


class GetSigningRouteTool(McpTool):
    spec = ToolSpec(
        name="get_signing_route",
        description=(
            "Ход маршрута подписания контрольной точки («Отправить на подписание»): статус и фаза, шаги с людьми и их "
            "состояниями, чья очередь сейчас, срок, причина остановки (документ изменился, вернули на доработку, "
            "участник ушёл) и последние события. У документов версия на подписи (sent) и есть ли изменения после "
            "отправки (changed): правка и пересборка маршрут не останавливают, подписывают версию на подписи. Без "
            "profile_id сводка по всем маршрутам проекта. Слоты: extra (добавлен сверх точки), optional (подпись "
            "необязательна на точке), статус skipped (пропущена); у участника state skipped, skipped_at и skippable. "
            "Маршрут из шаблона: preset (шаги, подписи сверх точки с условием when, отметки optional, что шаблон не "
            "добавил по условию, differs: чем маршрут отличается) и preset_hint; у слотов added_by (pack: добавил "
            "шаблон, author: автор) и preset_optional. Только чтение: согласовать, подписать, вернуть на доработку, "
            "пропустить подписанта и вернуть маршрут или место как в шаблоне можно только в интерфейсе."
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
                        "У контрольной точки нет маршрута подписания: его отправляет автор кнопкой «Отправить на "
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
            "согласовать и подписать, подписать итоговый PDF), с проектом, контрольной точкой, отправителем и сроком. "
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


def _other_route_text(doc: str, other: OtherRoute | None) -> str:
    """Документ держит маршрут другой точки: какой точки и что с ним сделать (отменить или снять с контроля)."""
    if other is None:
        return localized_error(
            f"документ {doc} уже на подписании по другому маршруту",
            f"document {doc} is already on another signing route",
        )
    ru = other.profile_name.get("ru") or other.profile_id
    en = other.profile_name.get("en") or other.profile_id
    if other.status is RouteStatus.completed:
        return localized_error(
            f"документ {doc} держит завершённый маршрут контрольной точки «{ru}» ({other.profile_id}): снимите его "
            "с контроля («Снять с контроля» на странице той точки)",
            f"document {doc} is held by the completed route of the checkpoint “{en}” ({other.profile_id}): stop "
            "tracking it (“Stop tracking” on that checkpoint page)",
        )
    return localized_error(
        f"документ {doc} на подписании в маршруте контрольной точки «{ru}» ({other.profile_id}): отмените тот "
        "маршрут на странице его точки",
        f"document {doc} is out for signing on the route of the checkpoint “{en}” ({other.profile_id}): cancel that "
        "route on its checkpoint page",
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
        BlockerCode.doc_in_other_route: _other_route_text(doc, blocker.other_route),
        BlockerCode.placement_off: localized_error(
            f"у слота {slot} документа {doc} не включено место на странице: включите размещение в интерфейсе",
            f"slot {slot} of document {doc} has no place on the page: turn its placement on in the interface",
        ),
        BlockerCode.no_participants: localized_error("в маршруте нет участников", "the route has no participants"),
        BlockerCode.nothing_changed: localized_error(
            "документы не менялись после отправки на подпись: новую версию отправлять нечего",
            "the documents have not changed since they were sent for signing: there is no new version to send",
        ),
    }
    return texts[blocker.code]


def _invited_text(preview: RoutePreview) -> list[str]:
    """Участники, которые ещё не приняли приглашение: через MCP маршрут с ними не уходит (раздел 6.8)."""
    return [
        localized_error(
            f"приглашение в проект ещё не принято: {p.name or p.participant.persona} ({p.participant.persona}); "
            "дождитесь принятия или отправьте маршрут из интерфейса",
            f"{p.name or p.participant.persona} ({p.participant.persona}) has not accepted the project invitation "
            "yet: wait for it or send the route from the interface",
        )
        for p in preview.participants
        if p.membership is Membership.invited
    ]


def _new_version_text(status: RouteStatus) -> str:
    """Отказ `new_version_in_ui` (12.10): маршрут идёт или завершён, а новая версия сбрасывает чужие согласия и
    подписи изменившихся документов. Это решение человека, MCP её не отправляет."""
    if status is RouteStatus.completed:
        ru = (
            "маршрут точки завершён. Отправить новую версию можно только в интерфейсе («Отправить новую версию» в "
            "карточке «Подписание»): она сбрасывает согласия и подписи изменившихся документов, это решение "
            "человека. Новый маршрут вместо этого начинается после «Снять с контроля» в интерфейсе"
        )
        en = (
            "the checkpoint route is completed. A new version can only be sent in the interface (“Send new "
            "version” on the “Signing” card): it resets approvals and signatures of the changed documents, which "
            "is a person's decision. A fresh route starts after “Stop tracking” in the interface instead"
        )
    else:
        ru = (
            "маршрут точки уже отправлен и идёт: его ход показывает get_signing_route. Отправить новую версию "
            "можно только в интерфейсе («Отправить новую версию» в карточке «Подписание»): она сбрасывает "
            "согласия и подписи изменившихся документов, это решение человека"
        )
        en = (
            "the checkpoint route is already sent and running: get_signing_route shows its progress. A new version "
            "can only be sent in the interface (“Send new version” on the “Signing” card): it resets approvals and "
            "signatures of the changed documents, which is a person's decision"
        )
    return localized_error(f"{ru} (new_version_in_ui)", f"{en} (new_version_in_ui)")


def _refusal(reasons: list[str]) -> ToolResult:
    head = localized_error("Маршрут не отправлен:", "The route was not sent:")
    return ToolResult.error("\n".join([head, *(f"- {reason}" for reason in reasons)]))


class SendForSigningTool(McpTool):
    spec = ToolSpec(
        name="send_for_signing",
        description=(
            "Отправить документы контрольной точки на подписание по маршруту, как кнопка «Отправить на подписание»: "
            "подписанты получат уведомления и письма по порядку шагов. Берёт сохранённый маршрут точки (черновик, "
            "остановленный или возвращённый на доработку: тогда это «Отправить заново»), а если его нет, создаёт "
            "из прежнего маршрута или пресета пака (порядок, подписи сверх точки по условию, отметки «необязательна», "
            "места подписей на страницах). Отправляет, только если ничего не мешает: документы собраны, "
            "все участники уже в проекте, подпись отправителя готова; иначе отвечает списком помех и ничего не "
            "отправляет. Если отправитель участник первого шага, отправка считается его согласованием. Ключом "
            "не подписывает и за других не согласует: это делается на странице подписи в интерфейсе. Новую версию "
            "идущего или завершённого маршрута не отправляет: её отправляет человек в интерфейсе, потому что она "
            "сбрасывает чужие согласия."
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
        # Завершённый маршрут черновик точки снял бы с контроля и начал заново: сначала смотрим текущий маршрут.
        summaries = await drafts.list_routes(project_id, profile_id)
        current = next((item.route for item in summaries if item.route.status is not RouteStatus.archived), None)
        if current is not None and current.status in NEW_VERSION_STATUSES:
            return _refusal([_new_version_text(current.status)])
        details, _ = await drafts.create(actor, project_id, profile_id)
        route = details.route
        if route.status not in EDITABLE_STATUSES:
            return _refusal([_new_version_text(route.status)])
        preview = await sending.preview(actor, project_id, route.id)
        reasons = [*(_blocker_text(b, preview) for b in preview.blockers), *_invited_text(preview)]
        if reasons:
            return _refusal(reasons)
        # Уходит ровно то, что показал этот предпросмотр: пересборка между ним и отправкой даёт отказ.
        expected = {doc.doc_id: doc.token for doc in preview.docs if doc.token is not None}
        # Новую версию идущего или завершённого маршрута MCP не отправляет: она сбрасывает чужие согласия (12.10).
        sent = await sending.send(actor, project_id, route.id, SendRequest(expected=expected, new_version=False))
        return json_result({"sent": True, "route": route_view(sent)})
