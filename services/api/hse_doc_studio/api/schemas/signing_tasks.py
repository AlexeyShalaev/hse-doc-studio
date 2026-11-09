"""«На подпись»: задачи человека по маршрутам подписания (`GET /account/signing-tasks`).

Зеркало `SigningTaskListSchema` фронтенда (entities/signing-route, docs/design/signing-route.md, раздел 8.2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

# Действие, которое ждут от человека прямо сейчас (`NextAction` ядра без `wait` и `done`).
SigningTaskActionName = Literal["approve", "approve_and_sign", "sign"]


class SigningProjectRef(StrictModel):
    id: str
    name: str


class SigningProfileRef(StrictModel):
    """Точка сдачи: id и название из пака (`{ru, en}`)."""

    id: str
    name: dict[str, str]


class SigningTaskSummary(StrictModel):
    project: SigningProjectRef
    route_id: str
    profile: SigningProfileRef
    round: int = Field(ge=0)
    # Кто отправил маршрут; null, если аккаунта больше нет.
    sender: str | None
    deadline: datetime | None
    next_action: SigningTaskActionName
    # С какого времени ждёт: запрос этого раунда.
    since: datetime | None


class SigningTaskList(StrictModel):
    items: list[SigningTaskSummary]
