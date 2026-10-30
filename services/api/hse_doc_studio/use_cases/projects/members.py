"""Участники проекта: роль человеку или группе и её снятие. Вызывает владелец проекта (гард: PROJECT_SETTINGS)."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import (
    IProjectAccessDirectory,
    IProjectMemberRepository,
    ProjectMemberGrant,
    ProjectMemberView,
    ProjectOwnership,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.orgs.protocols import IGroupRepository, IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import user_id_of

GRANTABLE_ROLES = (Role.reader, Role.reviewer, Role.editor)


async def _ownership(members: IProjectMemberRepository, project_id: UUID) -> ProjectOwnership:
    ownership = await members.get_ownership(project_id)
    if ownership is None:
        raise IdentityError(IdentityErrorCode.not_found)
    return ownership


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
    ) -> None:
        self._members = members
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
        return user.name


class RemoveProjectMemberUC:
    def __init__(self, members: IProjectMemberRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._members = members
        self._audit = audit
        self._uow = uow

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
