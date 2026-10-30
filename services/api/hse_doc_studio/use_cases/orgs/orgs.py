"""Организации: создание, просмотр, переименование, удаление."""

from __future__ import annotations

import uuid
from dataclasses import replace

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import is_reserved_slug, is_valid_slug, normalize_email
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.orgs.entities import ORG_NAME_MAX, Org, OrgMember, OrgRole, OrgSummary
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import load_context_by_slug, require_role, user_id_of

# Разрешает обычным пользователям заводить организации; по умолчанию создаёт только админ установки.
KEY_USERS_CREATE_ORGS = "orgs.users_can_create"


def clean_name(raw: str, limit: int) -> str:
    name = " ".join(raw.split())
    if not name or len(name) > limit:
        raise IdentityError(IdentityErrorCode.input_invalid)
    return name


def check_slug(slug: str) -> str:
    value = slug.strip().lower()
    if not is_valid_slug(value):
        raise IdentityError(IdentityErrorCode.slug_invalid)
    if is_reserved_slug(value):
        raise IdentityError(IdentityErrorCode.slug_reserved)
    return value


class ListMyOrgsUC:
    def __init__(self, orgs: IOrgRepository) -> None:
        self._orgs = orgs

    async def execute(self, actor: Actor) -> list[OrgSummary]:
        return await self._orgs.list_for_user(user_id_of(actor))


class GetOrgUC:
    def __init__(self, orgs: IOrgRepository) -> None:
        self._orgs = orgs

    async def execute(self, actor: Actor, slug: str) -> OrgSummary:
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        found = await self._orgs.summary(ctx.org, ctx.me.user_id)
        if found is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return found


class CreateOrgUC:
    def __init__(
        self,
        orgs: IOrgRepository,
        users: IUserRepository,
        settings: IInstanceSettingsRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._orgs = orgs
        self._users = users
        self._settings = settings
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, *, slug: str, name: str, owner_email: str | None = None) -> OrgSummary:
        """Создаёт админ установки, а обычный человек только когда админ это разрешил настройкой.
        Админ может назначить владельцем другого человека; иначе владельцем становится создатель."""
        creator = user_id_of(actor)
        if not actor.is_instance_admin:
            allowed = (await self._settings.get_all()).get(KEY_USERS_CREATE_ORGS) is True
            if not allowed or owner_email is not None:
                raise IdentityError(IdentityErrorCode.forbidden)
        value = check_slug(slug)
        title = clean_name(name, ORG_NAME_MAX)
        owner_id = creator
        if owner_email is not None:
            owner = await self._users.get_by_email(normalize_email(owner_email))
            if owner is None or not owner.can_sign_in:
                raise IdentityError(IdentityErrorCode.user_not_found)
            owner_id = owner.id
        now = self._clock()
        org = Org(id=f"org_{uuid.uuid4().hex}", slug=value, name=title, created_at=now, created_by=creator)
        async with self._uow.begin():
            await self._orgs.add(org)
            await self._orgs.add_member(OrgMember(org.id, owner_id, OrgRole.owner, now))
            await self._audit.record("org.create", actor_id=creator, target=org.id, details={"slug": value})
        return OrgSummary(org=org, my_role=OrgRole.owner, member_count=1, group_count=0, project_count=0)


class UpdateOrgUC:
    def __init__(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._orgs = orgs
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, slug: str, *, name: str) -> OrgSummary:
        """Переименовать может админ организации; адрес (slug) не меняется, на него ссылаются."""
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        require_role(ctx, OrgRole.admin)
        renamed = replace(ctx.org, name=clean_name(name, ORG_NAME_MAX))
        async with self._uow.begin():
            await self._orgs.update(renamed)
            await self._audit.record(
                "org.update", actor_id=ctx.me.user_id, target=ctx.org.id, details={"name": renamed.name}
            )
        found = await self._orgs.summary(renamed, ctx.me.user_id)
        if found is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return found


class DeleteOrgUC:
    def __init__(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._orgs = orgs
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, slug: str) -> None:
        """Удаляет владелец и только пустую организацию: проекты сначала передают или стирают окончательно."""
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        require_role(ctx, OrgRole.owner)
        async with self._uow.begin():
            if await self._orgs.count_projects(ctx.org.id) > 0:
                raise IdentityError(IdentityErrorCode.org_has_projects)
            await self._orgs.delete(ctx.org.id)
            await self._audit.record(
                "org.delete", actor_id=ctx.me.user_id, target=ctx.org.id, details={"slug": ctx.org.slug}
            )
