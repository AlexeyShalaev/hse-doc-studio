"""Участники проекта: роль человеку или группе и её снятие. Вызывает владелец проекта (гард: PROJECT_SETTINGS).

S10: нового человека в проект приводит только приглашение (`use_cases/projects/invitations.py`); напрямую меняется
роль уже добавленного человека и группы. Исключение: проект организации, человек её участник, а действует админ
этой организации (как с группой, D9).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.links import IShareLinkStore, RevokeReason
from hse_doc_studio.core.access.repositories import (
    IProjectAccessDirectory,
    IProjectMemberRepository,
    ProjectMemberGrant,
    ProjectMemberView,
    ProjectOwnership,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier, IProjectCards, IProjectMemberLookup
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.core.orgs.protocols import IGroupRepository, IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import user_id_of

GRANTABLE_ROLES = (Role.reader, Role.reviewer, Role.editor)


async def _ownership(members: IProjectMemberRepository, project_id: UUID) -> ProjectOwnership:
    ownership = await members.get_ownership(project_id)
    if ownership is None:
        raise IdentityError(IdentityErrorCode.not_found)
    return ownership


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SetProjectMemberUC:
    def __init__(
        self,
        members: IProjectMemberRepository,
        users: IUserRepository,
        groups: IGroupRepository,
        orgs: IOrgRepository,
        directory: IProjectAccessDirectory,
        audit: IAuditLog,
        uow: IUnitOfWork,
        member_roles: IProjectMemberLookup,
    ) -> None:
        self._members = members
        self._member_roles = member_roles
        self._directory = directory
        self._users = users
        self._groups = groups
        self._orgs = orgs
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, project_id: UUID, grant: ProjectMemberGrant) -> ProjectMemberView:
        """Назначает или меняет роль. Владельцем так не становятся: владелец проекта один, а организации
        владеют проектом через роль админа."""
        actor_id = user_id_of(actor)
        if grant.role not in GRANTABLE_ROLES:
            raise IdentityError(IdentityErrorCode.input_invalid)
        ownership = await _ownership(self._members, project_id)
        name = await self._principal_name(actor_id, project_id, ownership, grant)
        async with self._uow.begin():
            await self._members.set_member(project_id, grant)
            await self._audit.record(
                "project.member.set",
                actor_id=actor_id,
                target=str(project_id),
                details={"kind": grant.principal_kind, "principal_id": grant.principal_id, "role": grant.role.value},
            )
        return ProjectMemberView(grant, name)

    async def _principal_name(
        self, actor_id: str, project_id: UUID, ownership: ProjectOwnership, grant: ProjectMemberGrant
    ) -> str:
        if grant.principal_kind == "user":
            return await self._user_name(actor_id, project_id, ownership, grant.principal_id)
        group = await self._groups.get(grant.principal_id)
        if group is None:
            raise IdentityError(IdentityErrorCode.not_found)
        # Группу чужой организации назначить нельзя, даже зная её id.
        if ownership.owner_org_id is not None:
            allowed = group.org_id == ownership.owner_org_id
        else:
            allowed = await self._orgs.get_member(group.org_id, actor_id) is not None
        if not allowed:
            raise IdentityError(IdentityErrorCode.not_found)
        return group.name

    async def _user_name(self, actor_id: str, project_id: UUID, ownership: ProjectOwnership, user_id: str) -> str:
        if user_id == ownership.owner_user_id:
            raise IdentityError(IdentityErrorCode.input_invalid)
        # Назначить можно только тех, кого владелец вправе видеть (общая организация, уже открытые проекты);
        # для остальных ответ как для несуществующего, иначе по id можно проверять, есть ли такой человек.
        if not await self._directory.can_share_with(project_id, actor_id, user_id):
            raise IdentityError(IdentityErrorCode.not_found)
        user = await self._users.get(user_id)
        if user is None or not user.can_sign_in:
            raise IdentityError(IdentityErrorCode.not_found)
        known = await self._member_roles.direct_user_role(project_id, user_id) is not None
        if not known and not await self._direct_add_allowed(actor_id, ownership, user_id):
            # S10: нового человека приводит приглашение с подтверждением, а не мгновенное добавление.
            raise IdentityError(IdentityErrorCode.invitation_required, status=409)
        return user.name

    async def _direct_add_allowed(self, actor_id: str, ownership: ProjectOwnership, user_id: str) -> bool:
        """Исключение S10: админ организации-владельца добавляет её участника сразу."""
        org_id = ownership.owner_org_id
        if org_id is None:
            return False
        me = await self._orgs.get_member(org_id, actor_id)
        if me is None or me.role not in (OrgRole.owner, OrgRole.admin):
            return False
        return await self._orgs.get_member(org_id, user_id) is not None


class RemoveProjectMemberUC:
    def __init__(
        self,
        members: IProjectMemberRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        notifier: INotifier | None = None,
        cards: IProjectCards | None = None,
        users: IUserRepository | None = None,
        links: IShareLinkStore | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._members = members
        self._audit = audit
        self._uow = uow
        # invites: убранный человек получает уведомление `member_removed`.
        self._notifier = notifier
        self._cards = cards
        self._users = users
        # links: ссылки убранного человека отзываются вместе с его членством.
        self._links = links
        self._clock = clock

    async def execute(self, actor: Actor, project_id: UUID, principal_kind: str, principal_id: str) -> None:
        actor_id = user_id_of(actor)
        ownership = await _ownership(self._members, project_id)
        if principal_kind == "user" and principal_id == ownership.owner_user_id:
            raise IdentityError(IdentityErrorCode.input_invalid)
        async with self._uow.begin():
            if not await self._members.remove_member(project_id, principal_kind, principal_id):
                raise IdentityError(IdentityErrorCode.not_found)
            await self._audit.record(
                "project.member.remove",
                actor_id=actor_id,
                target=str(project_id),
                details={"kind": principal_kind, "principal_id": principal_id},
            )
            if principal_kind == "user":
                await self._revoke_links(actor_id, project_id, principal_id)
            if principal_kind == "user" and principal_id != actor_id:
                await self._notify_removed(actor_id, project_id, principal_id)

    async def _revoke_links(self, actor_id: str, project_id: UUID, user_id: str) -> None:
        """Ссылки, созданные убранным человеком, иначе пускали бы его (как гостя) в проект и после удаления."""
        if self._links is None:
            return
        revoked = await self._links.revoke_created_by(
            project_id, user_id, by=actor_id, reason=RevokeReason.member_removed, now=self._clock()
        )
        for link in revoked:
            await self._audit.record(
                "link.revoke",
                actor_id=actor_id,
                target=str(project_id),
                details={
                    "link_id": link.id,
                    "label": link.label,
                    "role": link.role.value,
                    "reason": RevokeReason.member_removed.value,
                },
            )

    async def _notify_removed(self, actor_id: str, project_id: UUID, user_id: str) -> None:
        if self._notifier is None or self._cards is None:
            return
        card = await self._cards.card(project_id)
        actor = await self._users.get(actor_id) if self._users is not None else None
        await self._notifier.notify(
            user_id,
            NotificationKind.member_removed,
            NotificationPayload(
                project_id=str(project_id),
                project_name=card.name if card else None,
                actor_name=actor.name if actor else None,
            ),
        )
