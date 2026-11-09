"""Персоны смотрящего в облаке: из членства проекта, а не из того, кто владелец ключа."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.infra.signatures.signer_scope import ServerSignerScope

from tests.factories import make_project
from tests.fixtures.actors import as_actor


class _Acl:
    def __init__(self, grants: dict[str, Grant]) -> None:
        self._grants = grants

    async def load_for(self, actor: Actor, project_id: UUID, *, include_links: bool = True) -> ProjectAcl | None:
        return ProjectAcl(project_id=str(project_id), grants=self._grants)

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        return None


async def test__server_scope__personas_from_membership() -> None:
    project = make_project()
    scope = ServerSignerScope(
        _Acl({"owner": Grant(Role.owner), "sup": Grant(Role.reviewer, persona_slug="supervisor")})
    )

    with as_actor(Actor.user("owner")):
        assert await scope.personas(project) == {"author"}
        assert scope.single_user() is False
    with as_actor(Actor.user("sup")):
        assert await scope.personas(project) == {"supervisor"}
    with as_actor(Actor.user("stranger")):
        assert await scope.personas(project) == frozenset()
