"""Сценарий готового текста приглашения: права как у приглашения, данные проекта и аккаунтов, запасной вариант."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind, Grant, ProjectAcl, Role
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.invitations.entities import ProjectCard
from hse_doc_studio.core.invitations.message import InvitationFacts, ProjectPerson
from hse_doc_studio.use_cases.projects.invitation_message import DraftInvitationMessageUC, InvitationDraftInput

PROJECT = uuid4()
ANNA = Actor(kind=ActorKind.user, id="u_anna", name="Анна Петрова")


def _user(user_id: str, name: str, email: str) -> User:
    return User(
        id=user_id,
        email=email,
        email_normalized=email,
        name=name,
        status=UserStatus.active,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        email_verified=True,
    )


class _Acl:
    def __init__(self, grants: dict[str, Grant]) -> None:
        self._grants = grants

    async def load_for(self, actor: Actor, project_id: UUID) -> ProjectAcl | None:
        return ProjectAcl(project_id=str(project_id), grants=self._grants) if project_id == PROJECT else None


class _Cards:
    async def card(self, project_id: UUID) -> ProjectCard | None:
        return ProjectCard(id=project_id, name="Диплом", owner_user_id="u_anna", owner_org_id=None, owner_name="Анна")


class _Users:
    def __init__(self, *users: User) -> None:
        self._by_id = {u.id: u for u in users}

    async def get(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)


class _Facts:
    def __init__(self, facts: InvitationFacts | None) -> None:
        self._facts = facts
        self.langs: list[Lang] = []

    async def facts(self, project_id: UUID, lang: Lang) -> InvitationFacts | None:
        self.langs.append(lang)
        return self._facts


FACTS = InvitationFacts(
    project_name="КП: ассистент",
    authors=(ProjectPerson(name="Анна Петрова", email="anna@hse.ru", group="МСПИН261", slug="petrova"),
             ProjectPerson(name="Пётр Иванов", email="petr@hse.ru", slug="ivanov")),
    supervisors={"supervisor": ProjectPerson(name="Хади Мухаммед")},
)  # fmt: skip
USERS = _Users(_user("u_anna", "Анна Петрова", "anna@hse.ru"), _user("u_petr", "petr", "petr@hse.ru"))


def _uc(
    *, grant: Grant | None = None, facts: InvitationFacts | None = FACTS
) -> tuple[DraftInvitationMessageUC, _Facts]:
    source = _Facts(facts)
    grants = {"u_anna": grant or Grant(role=Role.owner, can_share=True)}
    return DraftInvitationMessageUC(_Acl(grants), _Cards(), USERS, source), source  # type: ignore[arg-type]


async def test__draft__supervisor_by_persona_with_inviter_group() -> None:
    uc, source = _uc()

    text = await uc.execute(ANNA, PROJECT, InvitationDraftInput(role=Role.reviewer, persona="supervisor"), Lang.ru)

    assert text.startswith("Здравствуйте, Хади Мухаммед!\n\n")
    assert "в роли научного руководителя" in text
    assert text.endswith("С уважением,\nАнна Петрова, группа МСПИН261")
    assert source.langs == [Lang.ru]


async def test__draft__existing_user_is_matched_to_an_author_by_account_email() -> None:
    uc, _ = _uc()

    text = await uc.execute(ANNA, PROJECT, InvitationDraftInput(role=Role.editor, user_id="u_petr"), Lang.en)

    assert text.startswith("Hello, Пётр Иванов!\n\n")
    assert "as a co-author" in text


async def test__draft__unreadable_project_falls_back_to_the_project_card() -> None:
    uc, _ = _uc(facts=None)

    text = await uc.execute(ANNA, PROJECT, InvitationDraftInput(role=Role.reader, email="x@hse.ru"), Lang.ru)

    assert text == (
        "Здравствуйте!\n\nПриглашаю вас в проект «Диплом» в HSE Doc Studio в роли читателя. "
        "Здесь можно смотреть документы.\n\nС уважением,\nАнна Петрова"
    )


@pytest.mark.parametrize(
    ("grant", "code"),
    [
        (Grant(role=Role.reviewer), IdentityErrorCode.forbidden),
        (Grant(role=Role.editor, can_share=False), IdentityErrorCode.forbidden),
    ],
)
async def test__draft__needs_the_right_to_invite(grant: Grant, code: IdentityErrorCode) -> None:
    uc, _ = _uc(grant=grant)

    with pytest.raises(IdentityError) as caught:
        await uc.execute(ANNA, PROJECT, InvitationDraftInput(role=Role.reader), Lang.ru)

    assert caught.value.code is code


async def test__draft__foreign_project_is_not_found_and_owner_role_is_refused() -> None:
    uc, _ = _uc()

    with pytest.raises(IdentityError) as missing:
        await uc.execute(ANNA, uuid4(), InvitationDraftInput(role=Role.reader), Lang.ru)
    with pytest.raises(IdentityError) as owner:
        await uc.execute(ANNA, PROJECT, InvitationDraftInput(role=Role.owner), Lang.ru)

    assert missing.value.code is IdentityErrorCode.not_found
    assert owner.value.code is IdentityErrorCode.input_invalid
