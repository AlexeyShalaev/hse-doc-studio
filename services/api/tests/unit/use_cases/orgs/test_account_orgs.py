"""«Мои организации»: роль, названия своих групп, признак единственного владельца и выход."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.use_cases.orgs.groups import AddGroupMemberUC, CreateGroupUC
from hse_doc_studio.use_cases.orgs.members import LeaveOrgUC
from hse_doc_studio.use_cases.orgs.orgs import ListAccountOrgsUC

from tests.unit.use_cases.orgs.conftest import OrgWorld

OWN, ADM, MEM = OrgRole.owner, OrgRole.admin, OrgRole.member


async def test__list__only_own_orgs_with_group_names_and_sole_owner(world: OrgWorld) -> None:
    await world.org("alpha", anna=OWN, boris=MEM)
    await world.org("beta", anna=MEM, boris=OWN, carol=OWN)
    await world.org("gamma", carol=OWN)
    group = await world.uc(CreateGroupUC).execute(Actor.user("anna"), "alpha", name="Bertie")
    await world.uc(AddGroupMemberUC).execute(Actor.user("anna"), group.group.id, user_id="boris")

    anna = await world.uc(ListAccountOrgsUC).execute(Actor.user("anna"))
    boris = await world.uc(ListAccountOrgsUC).execute(Actor.user("boris"))

    assert [(x.summary.org.slug, x.summary.my_role, x.groups, x.sole_owner) for x in anna] == [
        ("alpha", OWN, (), True),
        ("beta", MEM, (), False),
    ]
    assert [(x.summary.org.slug, x.groups, x.sole_owner) for x in boris] == [
        ("alpha", ("Bertie",), False),
        ("beta", (), False),
    ]


async def test__leave__sole_owner_is_refused_and_member_leaves_with_groups(world: OrgWorld) -> None:
    org_id = await world.org("lab", anna=OWN, boris=MEM)

    with pytest.raises(IdentityError) as caught:
        await world.uc(LeaveOrgUC).execute(Actor.user("anna"), "lab")
    await world.uc(LeaveOrgUC).execute(Actor.user("boris"), "lab")

    assert caught.value.code is IdentityErrorCode.last_owner
    assert await world.orgs.get_member(org_id, "boris") is None
    assert [x.summary.org.slug for x in await world.uc(ListAccountOrgsUC).execute(Actor.user("boris"))] == []
