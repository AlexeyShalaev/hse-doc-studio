"""Запросы доступа (D10, S13): просьба о доступе к закрытому проекту и решение владельца.

Ответ на запрос одинаков для существующего и несуществующего проекта (202): запись появляется, только если проект
есть, просящий в нём не участник и не упирается в лимиты. Одобрение пишет участника напрямую: согласие дано самим
запросом.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import IProjectAclRepository, IProjectMemberRepository
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import (
    ACCESS_REQUEST_COOLDOWN,
    AccessRequest,
    AccessRequestStatus,
    AccessRequestView,
    MemberTerms,
    MyAccessRequestView,
    NotificationKind,
    NotificationPayload,
    stronger,
)
from hse_doc_studio.core.invitations.protocols import (
    IAccessRequestRepository,
    INotifier,
    IProjectCards,
    IProjectMemberLookup,
    IProjectPersonas,
)
from hse_doc_studio.core.listing import Found, Window, clamp_limit
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import user_id_of
from hse_doc_studio.use_cases.projects.invitations import actor_grant, check_persona, check_terms_within, member_grant


class CreateAccessRequestUC:
    def __init__(
        self,
        requests: IAccessRequestRepository,
        cards: IProjectCards,
        acl: IProjectAclRepository,
        notifier: INotifier,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._requests = requests
        self._cards = cards
        self._acl = acl
        self._notifier = notifier
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, project_id: UUID, message: str | None) -> bool:
        """True, если запись создана. Наружу результат не выдаётся (ответ всегда 202)."""
        user_id = user_id_of(actor)
        card = await self._cards.card(project_id)
        if card is None:
            return False
        loaded = await self._acl.load_for(actor, project_id)
        if loaded is not None and loaded.grant_for(actor) is not None:
            return False
        if await self._requests.pending_for(project_id, user_id) is not None:
            return False
        now = self._clock()
        denied_at = await self._requests.last_denied_at(project_id, user_id)
        if denied_at is not None and now - denied_at < ACCESS_REQUEST_COOLDOWN:
            return False
        request = AccessRequest(
            id=f"arq_{uuid.uuid4().hex}",
            project_id=project_id,
            user_id=user_id,
            message=(message or "").strip() or None,
            status=AccessRequestStatus.pending,
            created_at=now,
        )
        payload = NotificationPayload(
            project_id=str(project_id), project_name=card.name, actor_name=actor.name, ref_id=request.id
        )
        async with self._uow.begin():
            await self._requests.add(request)
            await self._audit.record(
                "project.access_request.create",
                actor_id=user_id,
                target=str(project_id),
                details={"request_id": request.id},
            )
            for manager in await self._cards.managers(project_id):
                await self._notifier.notify(
                    manager, NotificationKind.access_request, payload, dedupe_key=f"arq:{request.id}"
                )
        return True


class ListAccessRequestsUC:
    def __init__(self, requests: IAccessRequestRepository) -> None:
        self._requests = requests

    async def execute(self, project_id: UUID, *, pending_only: bool, window: Window) -> Found[AccessRequestView]:
        window = Window(clamp_limit(window.limit), max(0, window.offset))
        return await self._requests.page_for_project(project_id, pending_only=pending_only, window=window)


class _DecideRequest:
    def __init__(
        self,
        requests: IAccessRequestRepository,
        cards: IProjectCards,
        acl: IProjectAclRepository,
        members: IProjectMemberRepository,
        member_roles: IProjectMemberLookup,
        personas: IProjectPersonas,
        users: IUserRepository,
        notifier: INotifier,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._requests = requests
        self._cards = cards
        self._acl = acl
        self._members = members
        self._member_roles = member_roles
        self._personas = personas
        self._users = users
        self._notifier = notifier
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def _decide(
        self, actor: Actor, project_id: UUID, request_id: str, terms: MemberTerms | None
    ) -> AccessRequestView:
        actor_id = user_id_of(actor)
        grant = await actor_grant(self._acl, actor, project_id)
        if terms is not None:
            check_terms_within(terms, grant)
            await check_persona(self._personas, project_id, terms.persona)
        card = await self._cards.card(project_id)
        if card is None:
            raise IdentityError(IdentityErrorCode.not_found)
        now = self._clock()
        async with self._uow.begin():
            current = await self._requests.lock(request_id)
            if current is None or current.project_id != project_id:
                raise IdentityError(IdentityErrorCode.not_found)
            if current.status is not AccessRequestStatus.pending:
                raise IdentityError(IdentityErrorCode.access_request_decided)
            approved = terms is not None
            decided = replace(
                current,
                status=AccessRequestStatus.approved if approved else AccessRequestStatus.denied,
                decided_at=now,
                decided_by=actor_id,
                granted_role=terms.role if terms is not None else None,
            )
            await self._requests.update(decided)
            if terms is not None:
                await self._grant(card.owner_user_id, project_id, current.user_id, terms)
            await self._audit.record(
                f"project.access_request.{'approve' if approved else 'deny'}",
                actor_id=actor_id,
                target=str(project_id),
                details={"request_id": request_id, "role": terms.role.value if terms else None},
            )
            await self._notifier.notify(
                current.user_id,
                NotificationKind.access_request_decided,
                NotificationPayload(
                    project_id=str(project_id),
                    project_name=card.name if approved else None,
                    actor_name=actor.name or await self._name(actor_id),
                    role=terms.role.value if terms else None,
                    ref_id=request_id,
                    outcome="approved" if approved else "denied",
                ),
            )
        view = await self._requests.view(request_id)
        if view is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return view

    async def _grant(self, owner_user_id: str | None, project_id: UUID, user_id: str, terms: MemberTerms) -> None:
        if user_id == owner_user_id:
            return
        existing = await self._member_roles.direct_user_role(project_id, user_id)
        if existing is not None and stronger(existing, terms.role) is existing:
            return
        await self._members.set_member(project_id, member_grant(user_id, terms))

    async def _name(self, user_id: str) -> str | None:
        user = await self._users.get(user_id)
        return user.name if user else None


class ApproveAccessRequestUC(_DecideRequest):
    async def execute(self, actor: Actor, project_id: UUID, request_id: str, terms: MemberTerms) -> AccessRequestView:
        if terms.role is Role.owner:
            raise IdentityError(IdentityErrorCode.input_invalid)
        return await self._decide(actor, project_id, request_id, terms)


class DenyAccessRequestUC(_DecideRequest):
    async def execute(self, actor: Actor, project_id: UUID, request_id: str) -> AccessRequestView:
        return await self._decide(actor, project_id, request_id, None)


class ListMyAccessRequestsUC:
    def __init__(self, requests: IAccessRequestRepository) -> None:
        self._requests = requests

    async def execute(self, actor: Actor) -> list[MyAccessRequestView]:
        return await self._requests.list_for_user(user_id_of(actor))


class CancelAccessRequestUC:
    def __init__(
        self, requests: IAccessRequestRepository, audit: IAuditLog, uow: IUnitOfWork, clock: Clock = utc_now
    ) -> None:
        self._requests = requests
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, request_id: str) -> None:
        user_id = user_id_of(actor)
        async with self._uow.begin():
            current = await self._requests.lock(request_id)
            if current is None or current.user_id != user_id:
                raise IdentityError(IdentityErrorCode.not_found)
            if current.status is not AccessRequestStatus.pending:
                return
            await self._requests.update(
                replace(current, status=AccessRequestStatus.cancelled, decided_at=self._clock(), decided_by=user_id)
            )
            await self._audit.record(
                "project.access_request.cancel",
                actor_id=user_id,
                target=str(current.project_id),
                details={"request_id": request_id},
            )
