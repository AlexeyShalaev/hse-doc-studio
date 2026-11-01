"""Политика общего доступа организации (блок `sharing` в `orgs.policies`): смотрит участник, правит владелец или админ.

Ужесточение (запрет ссылок, понижение предела роли) ссылки не отзывает записью: они перестают действовать по
текущей политике при следующем запросе, а в списке ссылок помечаются «Не действует».
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.sharing_policy import OrgSharing, dump_org_sharing, parse_org_sharing
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import load_context_by_slug, require_role


@dataclass(frozen=True)
class OrgSharingView:
    sharing: OrgSharing
    editable: bool


def _plain(sharing: OrgSharing) -> dict[str, object]:
    return {k: getattr(v, "value", v) for k, v in asdict(sharing).items()}


class GetOrgSharingPolicyUC:
    def __init__(self, orgs: IOrgRepository) -> None:
        self._orgs = orgs

    async def execute(self, actor: Actor, slug: str) -> OrgSharingView:
        """Не участнику 404; участник видит политику, править её могут владелец и админ."""
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        return OrgSharingView(parse_org_sharing(ctx.org.policies), ctx.me.role.rank >= OrgRole.admin.rank)


class UpdateOrgSharingPolicyUC:
    def __init__(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._orgs = orgs
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, slug: str, sharing: OrgSharing) -> OrgSharingView:
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        require_role(ctx, OrgRole.admin)
        before = parse_org_sharing(ctx.org.policies)
        if before != sharing:
            org = ctx.org
            updated = replace(org, policies=dump_org_sharing(org.policies, sharing))
            async with self._uow.begin():
                await self._orgs.update(updated)
                await self._audit.record(
                    "org.sharing_policy_update",
                    actor_id=ctx.me.user_id,
                    target=org.id,
                    details={"before": _plain(before), "after": _plain(sharing)},
                )
        return OrgSharingView(sharing, editable=True)
