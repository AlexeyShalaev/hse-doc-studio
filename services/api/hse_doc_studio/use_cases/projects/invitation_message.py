"""Готовый текст приглашения в проект для формы «Пригласить» (и для любого клиента общего сценария приглашения).

Текст собирается по шаблону (`core.invitations.message`) из данных проекта и аккаунта приглашающего. Ничего не
сохраняет и не отправляет: человек правит текст и передаёт его в `CreateInvitationUC` полем `message`. Права те же,
что у приглашения (ACCESS_MANAGE и `actor_grant`).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.invitations.entities import GRANTABLE_ROLES
from hse_doc_studio.core.invitations.message import InvitationFacts, MessageRequest, compose_invitation_message
from hse_doc_studio.core.invitations.protocols import IInvitationFacts, IProjectCards
from hse_doc_studio.use_cases.orgs.access import user_id_of
from hse_doc_studio.use_cases.projects.invitations import actor_grant


@dataclass(frozen=True)
class InvitationDraftInput:
    role: Role
    persona: str | None = None
    email: str | None = None
    user_id: str | None = None


class DraftInvitationMessageUC:
    def __init__(
        self,
        acl: IProjectAclRepository,
        cards: IProjectCards,
        users: IUserRepository,
        facts: IInvitationFacts,
    ) -> None:
        self._acl = acl
        self._cards = cards
        self._users = users
        self._facts = facts

    async def execute(self, actor: Actor, project_id: UUID, draft: InvitationDraftInput, lang: Lang) -> str:
        if draft.role not in GRANTABLE_ROLES:
            raise IdentityError(IdentityErrorCode.input_invalid)
        actor_id = user_id_of(actor)
        await actor_grant(self._acl, actor, project_id)
        card = await self._cards.card(project_id)
        if card is None:
            raise IdentityError(IdentityErrorCode.not_found)
        facts = await self._facts.facts(project_id, lang) or InvitationFacts(project_name=card.name)
        inviter = await self._users.get(actor_id)
        invitee_email = draft.email
        if invitee_email is None and draft.user_id is not None:
            # Почта нужна только для сверки с авторами проекта; в ответ она не попадает.
            invitee = await self._users.get(draft.user_id)
            invitee_email = invitee.email_normalized if invitee is not None else None
        request = MessageRequest(
            role=draft.role,
            persona=draft.persona or None,
            invitee_email=invitee_email,
            inviter_name=(inviter.name if inviter else None) or actor.name,
            inviter_email=inviter.email_normalized if inviter else None,
        )
        return compose_invitation_message(facts, request, lang)
