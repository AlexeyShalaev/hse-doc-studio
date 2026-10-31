"""Стенд ревью: проект Анны из стенда ссылок, рецензент Рита и файл `notes.tex` с текстом."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Role

from tests.integration.api.sharing.conftest import (  # noqa: F401 — фикстуры стенда
    ORIGIN,
    USER_PASSWORD,
    Person,
    World,
    add_user,
    set_member,
    stand,
    world,
)

NOTES = "notes.tex"
TEXT = "Введение.\nМы изучаем совместную правку текста.\nЗаключение.\n"
QUOTE = "совместную правку"


class Review:
    def __init__(self, world: World) -> None:
        self.world = world
        self.project = world.project_id
        self.rita_id = add_user("rita@example.org", "Рита")
        set_member(self.project, self.rita_id, Role.reviewer)
        self.rita = Person(world.stand, "rita@example.org", USER_PASSWORD)
        written = world.anna.put(f"/api/v1/projects/{self.project}/files/{NOTES}", content=TEXT.encode())
        assert written.status_code == 204, written.text

    @property
    def base(self) -> str:
        return f"/api/v1/projects/{self.project}/review"

    def anchor(self, quote: str = QUOTE) -> dict[str, object]:
        start = TEXT.index(quote)
        return {
            "quote": quote,
            "prefix": TEXT[max(0, start - 20) : start],
            "suffix": TEXT[start + len(quote) : start + len(quote) + 20],
            "start": start,
            "end": start + len(quote),
        }

    def create(self, who: Person, body: str = "Уточните термин", **extra: object) -> dict[str, object]:
        response = who.post(
            f"{self.base}/threads", json={"path": NOTES, "anchor": self.anchor(), "body": body, **extra}
        )
        assert response.status_code == 201, response.text
        return dict(response.json())

    def inbox(self, who: Person, kind: str | None = None) -> list[dict[str, object]]:
        items = who.get("/api/v1/account/notifications").json()["items"]
        return [i for i in items if kind is None or i["kind"] == kind]


@pytest.fixture
def review(world: World) -> Review:
    return Review(world)
