"""Передача владения проектом (D11, S14).

Человеку: запись ждёт его подтверждения 7 дней. Организации, где инициатор владелец или админ: применяется сразу
после подтверждения именем проекта. Применение (`ApplyTransferUC`) идёт одной транзакцией по зафиксированной строке
проекта: если владелец за это время сменился, передача устаревает.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import IProjectMemberRepository, ProjectMemberGrant
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import (
    TRANSFER_TTL,
    NotificationKind,
    NotificationPayload,
    OwnerKind,
    ProjectCard,
    ProjectTransfer,
    TransferStatus,
    TransferView,
)
from hse_doc_studio.core.invitations.protocols import INotifier, IProjectCards, IProjectTransferRepository
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import user_id_of


class IPersonalWaitExpirer(Protocol):
    """Шов к очереди сборок: ждущие личного раннера прежнего владельца сборки уходят на общие (S14)."""

    async def expire_personal_wait(self, *, project_id: UUID) -> object: ...


@dataclass(frozen=True)
class TransferState:
    pending: bool
    view: TransferView | None


def _editor(user_id: str) -> ProjectMemberGrant:
    """Бывший владелец-человек остаётся редактором со всеми правами участника (S14)."""
    return ProjectMemberGrant(
        principal_kind="user", principal_id=user_id, role=Role.editor, can_share=True, show_sources=True,
        can_edit_all=True,
    )  # fmt: skip


class ApplyTransferUC:
    def __init__(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        members: IProjectMemberRepository,
        notifier: INotifier,
        audit: IAuditLog,
    ) -> None:
        self._transfers = transfers
        self._cards = cards
        self._members = members
        self._notifier = notifier
        self._audit = audit

    async def execute(self, transfer: ProjectTransfer, decided_by: str, now: datetime) -> ProjectCard | None:
        """Вызывается внутри транзакции вызывающего; очередь сборок он трогает после фиксации.

        None: владелец сменился с момента запроса, передача помечена `superseded` (вызывающий фиксирует это и
        отвечает `transfer_outdated`)."""
        card = await self._cards.lock_card(transfer.project_id)
        if card is None:
            raise IdentityError(IdentityErrorCode.not_found)
        if card.owner_kind != transfer.from_kind or card.owner_id != transfer.from_id:
            await self._transfers.update(replace(transfer, status=TransferStatus.superseded, decided_at=now))
            return None
        await self._cards.set_owner(card.id, transfer.to_kind, transfer.to_id)
        if transfer.to_kind == "user":
            # Владелец записью не назначается: прежняя прямая роль получателя не нужна.
            await self._members.remove_member(card.id, "user", transfer.to_id)
        if transfer.from_kind == "user":
            await self._members.set_member(card.id, _editor(transfer.from_id))
        elif transfer.initiated_by is not None and transfer.initiated_by != transfer.to_id:
            await self._members.set_member(card.id, _editor(transfer.initiated_by))
        accepted = replace(transfer, status=TransferStatus.accepted, decided_at=now, decided_by=decided_by)
        await self._transfers.update(accepted)
        await self._audit.record(
            "project.transfer.accept",
            actor_id=decided_by,
            target=str(card.id),
            details={
                "transfer_id": transfer.id,
                "from": f"{transfer.from_kind}:{transfer.from_id}",
                "to": f"{transfer.to_kind}:{transfer.to_id}",
            },
        )
        payload = NotificationPayload(
            project_id=str(card.id), project_name=card.name, ref_id=transfer.id, outcome="accepted"
        )
        for user_id in {transfer.initiated_by, transfer.to_id if transfer.to_kind == "user" else None} - {
            None,
            decided_by,
        }:
            await self._notifier.notify(str(user_id), NotificationKind.transfer_decided, payload)
        return card


class _TransferBase:
    def __init__(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._transfers = transfers
        self._cards = cards
        self._users = users
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def _card(self, project_id: UUID) -> ProjectCard:
        card = await self._cards.card(project_id)
        if card is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return card

    async def _name(self, user_id: str | None) -> str | None:
        if user_id is None:
            return None
        user = await self._users.get(user_id)
        return user.name if user else None


class StartTransferUC(_TransferBase):
    def __init__(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        orgs: IOrgRepository,
        apply: ApplyTransferUC,
        notifier: INotifier,
        queue: IPersonalWaitExpirer | None = None,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(transfers, cards, users, audit, uow, clock)
        self._orgs = orgs
        self._apply = apply
        self._notifier = notifier
        self._queue = queue

    async def execute(
        self,
        actor: Actor,
        project_id: UUID,
        to_kind: OwnerKind,
        to_id: str,
        *,
        message: str | None = None,
        confirm_name: str | None = None,
    ) -> TransferState:
        actor_id = user_id_of(actor)
        card = await self._card(project_id)
        target_id = await self._target(project_id, actor_id, to_kind, to_id)
        if to_kind == "org" and (confirm_name or "").strip() != card.name.strip():
            raise IdentityError(IdentityErrorCode.confirm_name_mismatch)
        now = self._clock()
        transfer = ProjectTransfer(
            id=f"trf_{uuid.uuid4().hex}",
            project_id=project_id,
            from_kind=card.owner_kind,
            from_id=card.owner_id,
            to_kind=to_kind,
            to_id=target_id,
            initiated_by=actor_id,
            message=(message or "").strip() or None,
            status=TransferStatus.pending,
            created_at=now,
            expires_at=now + TRANSFER_TTL,
        )
        async with self._uow.begin():
            await self._transfers.supersede_pending(project_id, now)
            await self._transfers.add(transfer)
            await self._audit.record(
                "project.transfer.start",
                actor_id=actor_id,
                target=str(project_id),
                details={
                    "transfer_id": transfer.id,
                    "from": f"{transfer.from_kind}:{transfer.from_id}",
                    "to": f"{to_kind}:{target_id}",
                },
            )
            if to_kind == "org":
                # S14: организации, где инициатор владелец или админ, проект переходит сразу. Строка проекта
                # зафиксирована: владелец не мог смениться между чтением карточки и этой транзакцией.
                if await self._apply.execute(transfer, actor_id, now) is None:
                    raise IdentityError(IdentityErrorCode.transfer_outdated)
            else:
                await self._notifier.notify(
                    target_id,
                    NotificationKind.transfer_request,
                    NotificationPayload(
                        project_id=str(project_id),
                        project_name=card.name,
                        actor_name=actor.name or await self._name(actor_id),
                        role=Role.editor.value if card.owner_kind == "user" else None,
                        ref_id=transfer.id,
                    ),
                    dedupe_key=f"trf:{transfer.id}",
                )
        if to_kind == "org" and self._queue is not None:
            await self._queue.expire_personal_wait(project_id=project_id)
        view = await self._transfers.view(transfer.id)
        return TransferState(pending=to_kind != "org", view=view if to_kind != "org" else None)

    async def _target(self, project_id: UUID, actor_id: str, to_kind: OwnerKind, to_id: str) -> str:
        """Id получателя; организацию адресует slug. Не кандидат: 404, как несуществующий (T11)."""
        target_id = to_id
        if to_kind == "org":
            org = await self._orgs.get_by_slug(to_id)
            if org is None:
                raise IdentityError(IdentityErrorCode.not_found)
            target_id = org.id
        if not await self._cards.is_transfer_candidate(project_id, actor_id, to_kind, target_id):
            raise IdentityError(IdentityErrorCode.not_found)
        return target_id


class CancelTransferUC(_TransferBase):
    async def execute(self, actor: Actor, project_id: UUID) -> None:
        actor_id = user_id_of(actor)
        async with self._uow.begin():
            pending = await self._transfers.pending_for_project(project_id)
            if pending is None:
                raise IdentityError(IdentityErrorCode.not_found)
            await self._transfers.update(
                replace(pending, status=TransferStatus.cancelled, decided_at=self._clock(), decided_by=actor_id)
            )
            await self._audit.record(
                "project.transfer.cancel",
                actor_id=actor_id,
                target=str(project_id),
                details={"transfer_id": pending.id},
            )


class GetTransferStateUC(_TransferBase):
    async def execute(self, project_id: UUID, *, can_transfer: bool) -> TransferState:
        """Детали получателя видит только тот, кто вправе передать проект; остальным только признак."""
        pending = await self._transfers.pending_for_project(project_id)
        if pending is None or pending.expired(self._clock()):
            return TransferState(pending=False, view=None)
        if not can_transfer:
            return TransferState(pending=True, view=None)
        return TransferState(pending=True, view=await self._transfers.view(pending.id))


class ListMyTransfersUC(_TransferBase):
    async def execute(self, actor: Actor) -> list[TransferView]:
        return await self._transfers.list_for_user(user_id_of(actor))


class _DecideTransfer(_TransferBase):
    def __init__(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        apply: ApplyTransferUC,
        notifier: INotifier,
        queue: IPersonalWaitExpirer | None = None,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(transfers, cards, users, audit, uow, clock)
        self._apply = apply
        self._notifier = notifier
        self._queue = queue

    async def _locked(self, actor_id: str, transfer_id: str) -> ProjectTransfer:
        current = await self._transfers.lock(transfer_id)
        if current is None or current.to_kind != "user" or current.to_id != actor_id:
            raise IdentityError(IdentityErrorCode.not_found)
        if current.status is not TransferStatus.pending:
            raise IdentityError(IdentityErrorCode.not_found)
        return current

    async def _result(self, transfer_id: str) -> TransferView:
        view = await self._transfers.view(transfer_id)
        if view is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return view


class AcceptTransferUC(_DecideTransfer):
    async def execute(self, actor: Actor, transfer_id: str) -> TransferView:
        actor_id = user_id_of(actor)
        now = self._clock()
        async with self._uow.begin():
            current = await self._locked(actor_id, transfer_id)
            if current.expires_at <= now:
                raise IdentityError(IdentityErrorCode.transfer_expired)
            applied = await self._apply.execute(current, actor_id, now)
        if applied is None:
            raise IdentityError(IdentityErrorCode.transfer_outdated)
        if self._queue is not None:
            await self._queue.expire_personal_wait(project_id=current.project_id)
        return await self._result(transfer_id)


class DeclineTransferUC(_DecideTransfer):
    async def execute(self, actor: Actor, transfer_id: str) -> TransferView:
        actor_id = user_id_of(actor)
        now = self._clock()
        async with self._uow.begin():
            current = await self._locked(actor_id, transfer_id)
            await self._transfers.update(
                replace(current, status=TransferStatus.declined, decided_at=now, decided_by=actor_id)
            )
            await self._audit.record(
                "project.transfer.decline",
                actor_id=actor_id,
                target=str(current.project_id),
                details={"transfer_id": transfer_id},
            )
            card = await self._cards.card(current.project_id)
            if current.initiated_by is not None:
                await self._notifier.notify(
                    current.initiated_by,
                    NotificationKind.transfer_decided,
                    NotificationPayload(
                        project_id=str(current.project_id),
                        project_name=card.name if card else None,
                        actor_name=actor.name or await self._name(actor_id),
                        ref_id=transfer_id,
                        outcome="declined",
                    ),
                )
        return await self._result(transfer_id)
