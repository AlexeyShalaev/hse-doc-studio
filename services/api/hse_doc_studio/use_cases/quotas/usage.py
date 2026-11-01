"""Страницы «Использование»: человек видит свои расходы и расходы своих организаций."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.jobs.quotas import org_key
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.quotas.policy import Assessment
from hse_doc_studio.use_cases.orgs.access import user_id_of
from hse_doc_studio.use_cases.quotas.gate import QuotaGate


@dataclass(frozen=True)
class OwnerUsage:
    owner_id: str
    owner_name: str
    lines: list[Assessment]


@dataclass(frozen=True)
class UserUsage:
    user: OwnerUsage
    orgs: list[OwnerUsage]


class GetMyUsageUC:
    def __init__(self, gate: QuotaGate, orgs: IOrgRepository) -> None:
        self._gate = gate
        self._orgs = orgs

    async def execute(self, actor: Actor) -> UserUsage:
        user_id = user_id_of(actor)
        try:
            uid = UUID(user_id)
        except ValueError as exc:
            raise IdentityError(IdentityErrorCode.not_found) from exc
        memberships = await self._orgs.list_for_user(user_id)
        # Значение «на участника» берётся у организации человека, если она одна: иначе неясно, чьё правило применять.
        member_org = org_key(memberships[0].org.id) if len(memberships) == 1 else None
        mine = OwnerUsage(user_id, actor.name or user_id, await self._gate.lines_for_user(uid, member_org))
        orgs = [
            OwnerUsage(item.org.id, item.org.name, await self._gate.lines_for_org(item.org.id)) for item in memberships
        ]
        return UserUsage(mine, orgs)


class GetOrgUsageUC:
    def __init__(self, gate: QuotaGate, orgs: IOrgRepository) -> None:
        self._gate = gate
        self._orgs = orgs

    async def execute(self, actor: Actor, slug: str) -> OwnerUsage:
        user_id = user_id_of(actor)
        org = await self._orgs.get_by_slug(slug)
        # Чужая организация и несуществующая выглядят одинаково.
        if org is None or await self._orgs.get_member(org.id, user_id) is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return OwnerUsage(org.id, org.name, await self._gate.lines_for_org(org.id))
