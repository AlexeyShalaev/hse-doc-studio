"""Контракт «люди в проекте» (docs/design/connected-devices.md, раздел 15): сигнал вкладки и список онлайн."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.devices.people import (
    DOC_ID_RE,
    SESSION_ID_RE,
    Activity,
    ProjectPeople,
    WebSignal,
    sanitize_doc,
)

ReportedActivity = Literal["editing", "viewing", "reviewing", "building", "browsing"]
ShownActivity = Literal["editing", "viewing", "reviewing", "building", "browsing", "local"]


class PresenceSignalRequest(StrictModel):
    # Случайный идентификатор вкладки (живёт в sessionStorage): две вкладки одного человека это одна иконка.
    session_id: str = Field(min_length=8, max_length=64, pattern=f"^{SESSION_ID_RE.pattern}$")
    activity: ReportedActivity = "browsing"
    # Документ проекта (идентификатор экземпляра), не глубже; без документа null.
    doc_id: str | None = Field(default=None, max_length=128, pattern=f"^{DOC_ID_RE.pattern}$")

    def to_signal(self) -> WebSignal:
        return WebSignal(self.session_id, Activity(self.activity), sanitize_doc(self.doc_id))


class PersonOnlineOut(StrictModel):
    user_id: str
    name: str
    initials: str
    # Тот же цвет, что у курсора человека в документе.
    color: str
    role: Literal["reader", "reviewer", "editor", "owner"]
    me: bool
    activity: ShownActivity
    doc_id: str | None
    channels: list[Literal["web", "studio"]]
    seen_at: datetime


class ProjectPeopleResponse(StrictModel):
    interval_s: int
    online_window_s: int
    total: int
    people: list[PersonOnlineOut]


def map_people_online(found: ProjectPeople) -> ProjectPeopleResponse:
    return ProjectPeopleResponse(
        interval_s=found.interval_s,
        online_window_s=found.online_window_s,
        total=found.total,
        people=[
            PersonOnlineOut(
                user_id=p.user_id,
                name=p.name,
                initials=p.initials,
                color=p.color,
                role=p.role.value,
                me=p.me,
                activity=p.activity.value,
                doc_id=p.doc_id,
                channels=[c.value for c in p.channels],
                seen_at=p.seen_at,
            )
            for p in found.people
        ],
    )
