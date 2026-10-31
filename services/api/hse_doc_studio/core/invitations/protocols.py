"""Порты трека invites: хранилища приглашений, запросов, передач, уведомлений и сведения о проекте."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.invitations.entities import (
    AccessRequest,
    AccessRequestView,
    InvitationView,
    MyAccessRequestView,
    MyInvitationView,
    Notification,
    NotificationKind,
    NotificationPayload,
    OwnerKind,
    ProjectCard,
    ProjectInvitation,
    ProjectTransfer,
    TransferView,
)
from hse_doc_studio.core.listing import Found, Window


class INotificationRepository(Protocol):
    async def add(
        self,
        user_id: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        dedupe_key: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Повтор с тем же `dedupe_key` не создаёт второй строки, а поднимает прежнюю как непрочитанную."""
        ...

    async def page(self, user_id: str, *, unread_only: bool, window: Window) -> Found[Notification]: ...
    async def unread_count(self, user_id: str) -> int: ...
    async def mark_read(self, user_id: str, ids: Sequence[str] | None, now: datetime) -> int:
        """`ids=None` отмечает все непрочитанные; чужие id не трогаются."""
        ...

    async def purge(self, before: datetime) -> int: ...


class INotifier(Protocol):
    """Уведомление в Студии и письмо, если SMTP есть и вид письма предусмотрен (S15)."""

    async def notify(
        self,
        user_id: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        dedupe_key: str | None = None,
    ) -> None: ...


class IProjectInvitationRepository(Protocol):
    async def add(self, invitation: ProjectInvitation) -> None: ...
    async def get(self, invitation_id: str) -> ProjectInvitation | None: ...
    async def get_by_token_hash(self, token_hash: str) -> ProjectInvitation | None: ...
    async def lock(self, invitation_id: str) -> ProjectInvitation | None:
        """Строка под `FOR UPDATE` до конца транзакции: два принятия одного приглашения не пройдут оба."""
        ...

    async def update(self, invitation: ProjectInvitation) -> None: ...
    async def pending_for_user(self, project_id: UUID, user_id: str) -> ProjectInvitation | None: ...
    async def pending_for_email(self, project_id: UUID, email: str) -> ProjectInvitation | None: ...
    async def count_pending(self, project_id: UUID, now: datetime) -> int:
        """Действующие ожидающие приглашения проекта (просроченные не считаются)."""
        ...

    async def page_for_project(
        self, project_id: UUID, *, pending_only: bool, window: Window
    ) -> Found[InvitationView]: ...
    async def list_for_user(self, user_id: str) -> list[MyInvitationView]:
        """Ожидающие приглашения человеку (и просроченные, чтобы сказать «срок истёк»)."""
        ...

    async def my_view(self, invitation_id: str) -> MyInvitationView | None: ...
    async def attach_email(self, email: str, user_id: str) -> list[ProjectInvitation]:
        """Ожидающие приглашения на почту без адресата привязываются к человеку; возвращает привязанные."""
        ...

    async def count_pending_for_user(self, user_id: str, now: datetime) -> int: ...


class IAccessRequestRepository(Protocol):
    async def add(self, request: AccessRequest) -> None: ...
    async def get(self, request_id: str) -> AccessRequest | None: ...
    async def lock(self, request_id: str) -> AccessRequest | None: ...
    async def update(self, request: AccessRequest) -> None: ...
    async def pending_for(self, project_id: UUID, user_id: str) -> AccessRequest | None: ...
    async def last_denied_at(self, project_id: UUID, user_id: str) -> datetime | None: ...
    async def page_for_project(
        self, project_id: UUID, *, pending_only: bool, window: Window
    ) -> Found[AccessRequestView]: ...
    async def view(self, request_id: str) -> AccessRequestView | None: ...
    async def list_for_user(self, user_id: str) -> list[MyAccessRequestView]: ...
    async def count_pending_managed(self, user_id: str) -> int:
        """Ожидающие запросы в проектах, где человек решает доступ (владелец, админ организации, `can_share`)."""
        ...


class IProjectTransferRepository(Protocol):
    async def add(self, transfer: ProjectTransfer) -> None: ...
    async def get(self, transfer_id: str) -> ProjectTransfer | None: ...
    async def lock(self, transfer_id: str) -> ProjectTransfer | None: ...
    async def update(self, transfer: ProjectTransfer) -> None: ...
    async def pending_for_project(self, project_id: UUID) -> ProjectTransfer | None: ...
    async def supersede_pending(self, project_id: UUID, now: datetime) -> int: ...
    async def view(self, transfer_id: str) -> TransferView | None: ...
    async def list_for_user(self, user_id: str) -> list[TransferView]:
        """Ожидающие передачи человеку (и просроченные)."""
        ...

    async def count_pending_for_user(self, user_id: str, now: datetime) -> int: ...


class IProjectCards(Protocol):
    """Сведения о проекте для приглашений и передачи владения (каталог проектов в БД)."""

    async def card(self, project_id: UUID) -> ProjectCard | None:
        """None, если проекта нет или он удалён."""
        ...

    async def lock_card(self, project_id: UUID) -> ProjectCard | None:
        """То же под `FOR UPDATE`: смена владельца идёт по зафиксированной строке."""
        ...

    async def set_owner(self, project_id: UUID, kind: OwnerKind, owner_id: str) -> None:
        """Новый владелец; политика сборок соавторов сбрасывается на общие раннеры (S14)."""
        ...

    async def managers(self, project_id: UUID) -> list[str]:
        """Кто решает доступ прямым правом: владелец-человек или владельцы и админы организации-владельца."""
        ...

    async def is_transfer_candidate(self, project_id: UUID, actor_id: str, kind: OwnerKind, target_id: str) -> bool:
        """Тот же круг, что у `transfer_candidates`: у организации `target_id` это её id."""
        ...


class IProjectPersonas(Protocol):
    async def personas(self, project_id: UUID) -> frozenset[str] | None:
        """Слаги авторов и роли руководителей из `project.json`; None, если проект не прочитать."""
        ...


class IInvitationMailer(Protocol):
    """Письмо о приглашении со ссылкой: True, если ушло по SMTP (иначе ссылку отдают пригласившему)."""

    @property
    def enabled(self) -> bool: ...

    async def send_invitation(
        self,
        to_email: str,
        *,
        project_name: str,
        inviter_name: str,
        role: str,
        link: str,
        message: str | None,
        locale: str | None,
    ) -> bool: ...
