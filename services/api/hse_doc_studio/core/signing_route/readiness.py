"""Готовность маршрута к отправке: помехи предпросмотра и отказы отправки (docs/design/signing-route.md, раздел 8).

Помехи считает сценарий предпросмотра; отправка повторяет тот же расчёт и отказывает с теми же помехами, если они
есть (`route_blocked`), или если документы изменились после показа (`doc_changed`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signing_route.entities import RouteConflictError, RouteStatus


class BlockerCode(StrEnum):
    """Что мешает отправить маршрут (`blockers[].code` предпросмотра)."""

    not_built = "not_built"  # документ не собран
    participant_missing = "participant_missing"  # человека нет в проекте с персоной своего шага
    slot_unassigned = "slot_unassigned"  # у слота точки нет участника с персоной владельца слота
    sender_not_ready = "sender_not_ready"  # картинка или данные плашки отправителя не готовы
    doc_in_other_route = "doc_in_other_route"  # документ держит другой маршрут
    # У слота с видимой меткой (картинка, плашка ЭП) нет включённого места на странице: его нельзя подписать.
    placement_off = "placement_off"
    no_participants = "no_participants"
    # Идущий или завершённый маршрут без изменений после отправки: новую версию отправлять нечего (12.6).
    nothing_changed = "nothing_changed"


@dataclass(frozen=True)
class OtherRoute:
    """Маршрут, который держит документ (`doc_in_other_route`): его контрольная точка и статус.

    По ним помеха говорит, где и что сделать: идущий, остановленный и возвращённый маршрут отменяют на странице его
    точки, завершённый снимают с контроля там же (раздел 5.3). Документ держит один маршрут (5.8).
    """

    route_id: UUID
    profile_id: str
    profile_name: Mapping[str, str]
    status: RouteStatus


@dataclass(frozen=True)
class Blocker:
    code: BlockerCode
    doc_id: str | None = None
    slot_id: str | None = None
    participant_id: UUID | None = None
    # Только у `doc_in_other_route`: какой маршрут держит документ.
    other_route: OtherRoute | None = None


class RouteBlockedError(RouteConflictError):
    """Отправка, пока предпросмотр называет помехи (409 `route_blocked`)."""

    def __init__(self, blockers: Sequence[Blocker]) -> None:
        super().__init__(
            "route_blocked",
            localized_error(
                "Маршрут нельзя отправить: исправьте то, что мешает", "The route cannot be sent: fix what blocks it"
            ),
        )
        self.blockers = tuple(blockers)


class DocChangedError(RouteConflictError):
    """Отпечаток документа не совпал с тем, что видел человек (409 `doc_changed`)."""

    def __init__(self, doc_ids: Sequence[str]) -> None:
        super().__init__(
            "doc_changed",
            localized_error("Документ изменился, откройте заново", "The document has changed, reload it"),
        )
        self.doc_ids = tuple(doc_ids)
