"""Общее для сценариев уведомлений маршрута: люди, маршрут «автор, научрук, академрук» и его прогон."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.signing_route.entities import SigningRoute
from hse_doc_studio.core.signing_route.ports import RouteLabels

from tests.fakes.signing_routes import StaticRouteContext
from tests.unit.core.signing_route.world import T0, Driver, World, make_route, participant

PROFILE_NAME = {"ru": "Заявка на тему КП", "en": "Topic application"}


@dataclass
class Users:
    """`IUserRepository.get` по id: имя и язык аккаунта."""

    people: dict[str, User] = field(default_factory=dict)

    def add(self, user_id: UUID | None, name: str, locale: str | None = None) -> None:
        assert user_id is not None
        self.people[user_id.hex] = User(
            id=user_id.hex,
            email=f"{name}@x.org",
            email_normalized=f"{name}@x.org",
            name=name,
            status=UserStatus.active,
            created_at=T0,
            email_verified=True,
            locale=locale,
        )

    async def get(self, user_id: str) -> User | None:
        return self.people.get(user_id)


@dataclass(frozen=True)
class Sent:
    user_id: str
    kind: NotificationKind
    payload: NotificationPayload
    dedupe_key: str | None
    mail: bool


@dataclass
class Inbox:
    """`INotifier`: запоминает уведомления вместе с решением о письме."""

    sent: list[Sent] = field(default_factory=list)

    async def notify(
        self,
        user_id: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        dedupe_key: str | None = None,
        mail: bool = True,
    ) -> None:
        self.sent.append(Sent(user_id, kind, payload, dedupe_key, mail))


def three_steps(world: World | None = None) -> Driver:
    """Автор, научрук и академрук картинкой, каждый своим шагом; маршрут ещё не отправлен."""
    world = world or World(
        {"author": SignMode.image, "supervisor": SignMode.image, "academic_supervisor": SignMode.image}
    )
    route = make_route(
        [
            participant(1, "author", ["author"]),
            participant(2, "supervisor", ["supervisor"]),
            participant(3, "academic_supervisor", ["academic_supervisor"]),
        ]
    )
    return Driver(world, route)


def context(driver: Driver, project_name: str = "Bertie") -> StaticRouteContext:
    """Факты из мира прогона и подписи проекта маршрута."""
    return StaticRouteContext(
        facts_of=lambda _route: driver.world.facts(),
        projects={driver.route.project_id: RouteLabels(project_name, PROFILE_NAME)},
    )


def people(route: SigningRoute) -> Users:
    users = Users()
    for p, (name, locale) in zip(route.participants, (("Иван", "ru"), ("Пётр", "ru"), ("Sam", "en")), strict=False):
        users.add(p.user_id, name, locale)
    return users
