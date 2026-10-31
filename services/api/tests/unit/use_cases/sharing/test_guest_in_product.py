"""Гость в продукте: плательщик сборки (S7), подпись снимков гостя, что гость видит в панели «Доступ»."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import ActorRequired
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.access.links import LinkProject, LinkRole, ShareLink
from hse_doc_studio.core.access.repositories import ProjectAccessRow
from hse_doc_studio.core.identity.commit_identity import guest_commit_identity
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.listing import Found
from hse_doc_studio.use_cases.sharing.payer import GuestBuildPayer
from hse_doc_studio.use_cases.sharing.visibility import visible_rows_for

pytestmark = pytest.mark.unit

PROJECT = uuid4()
CREATOR = uuid4().hex
OWNER = uuid4().hex
NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _link(created_by: str | None) -> ShareLink:
    return ShareLink(
        id="lnk_1",
        project_id=PROJECT,
        label="Для группы",
        role=LinkRole.editor,
        show_sources=True,
        require_login=False,
        has_password=False,
        token_prefix="abcdefgh",
        created_by=created_by,
        created_at=NOW,
        updated_at=NOW,
        expires_at=None,
        revoked_at=None,
        revoke_reason=None,
        replaced_by=None,
        last_opened_at=None,
    )


class _Store:
    def __init__(self, link: ShareLink | None, owner_user_id: str | None) -> None:
        self.link = link
        self.owner_user_id = owner_user_id

    async def get(self, link_id: str) -> ShareLink | None:  # noqa: ARG002
        return self.link

    async def project(self, project_id: UUID) -> LinkProject | None:
        return LinkProject(project_id, "ВКР", self.owner_user_id, None if self.owner_user_id else "org", "Анна", False)


class _Acl:
    def __init__(self, grants: dict[str, Grant]) -> None:
        self.grants = grants

    async def load_for(self, actor: Actor, project_id: UUID, *, include_links: bool = True) -> ProjectAcl | None:
        assert include_links is False
        grant = self.grants.get(actor.id or "")
        return ProjectAcl(str(project_id), grants={actor.id or "": grant}) if grant else None


GUEST = Actor.guest("gs_1", "Борис", link_id="lnk_1")


async def test__payer__user_pays_himself() -> None:
    payer = GuestBuildPayer(_Store(None, OWNER), _Acl({}))  # type: ignore[arg-type]

    assert await payer.payer_for(Actor.user(OWNER), PROJECT) == UUID(OWNER)


async def test__payer__guest_uses_creator_who_still_shares() -> None:
    acl = _Acl({CREATOR: Grant(Role.editor, can_share=True)})
    payer = GuestBuildPayer(_Store(_link(CREATOR), OWNER), acl)  # type: ignore[arg-type]

    assert await payer.payer_for(GUEST, PROJECT) == UUID(CREATOR)


async def test__payer__creator_lost_share__owner_pays() -> None:
    acl = _Acl({CREATOR: Grant(Role.editor, can_share=False)})
    payer = GuestBuildPayer(_Store(_link(CREATOR), OWNER), acl)  # type: ignore[arg-type]

    assert await payer.payer_for(GUEST, PROJECT) == UUID(OWNER)


async def test__payer__org_project_without_creator__unavailable() -> None:
    payer = GuestBuildPayer(_Store(_link(None), None), _Acl({}))  # type: ignore[arg-type]

    with pytest.raises(IdentityError) as caught:
        await payer.payer_for(GUEST, PROJECT)
    assert caught.value.code is IdentityErrorCode.guest_build_unavailable


async def test__payer__guest_without_link_is_refused() -> None:
    payer = GuestBuildPayer(_Store(None, OWNER), _Acl({}))  # type: ignore[arg-type]

    with pytest.raises(ActorRequired):
        await payer.payer_for(Actor.guest("gs_1"), PROJECT)


def test__guest_commit_identity() -> None:
    author = guest_commit_identity("Борис", "lnk_1", "Для группы", "noreply.studio.example.org")

    assert author.name == "Гость: Борис (ссылка «Для группы»)"
    assert author.email == "guest+lnk_1@noreply.studio.example.org"
    assert guest_commit_identity(None, "lnk_1", "x", "d").name == "Гость: без имени (ссылка «x»)"


def _rows() -> Found[ProjectAccessRow]:
    return Found(
        [
            ProjectAccessRow("user", OWNER, "Анна", None, Role.owner, locked=True),
            ProjectAccessRow("user", CREATOR, "Вера", None, Role.editor, locked=False),
        ],
        2,
    )


def test__visible_rows__guest_and_link_user_see_only_pinned() -> None:
    assert visible_rows_for(Actor.user(CREATOR), _rows()) == _rows()
    for actor in (GUEST, Actor.user("dina").with_link("lnk_1")):
        found = visible_rows_for(actor, _rows())
        assert [r.name for r in found.items] == ["Анна"]
        assert found.total == 1
