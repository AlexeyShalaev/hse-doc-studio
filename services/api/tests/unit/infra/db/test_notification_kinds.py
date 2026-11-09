"""Виды уведомлений совпадают везде: перечисление ядра, проверка в базе, форма API и уведомления маршрута."""

from __future__ import annotations

from typing import get_args

from hse_doc_studio.api.schemas.invitations import NotificationKindName
from hse_doc_studio.core.invitations.entities import NotificationKind
from hse_doc_studio.core.signing_route.entities import Notice
from hse_doc_studio.infra.db.orm.invitations import NOTIFICATION_KINDS


def test__notification_kinds__core_db_check_and_api_agree() -> None:
    kinds = {kind.value for kind in NotificationKind}

    assert set(NOTIFICATION_KINDS) == kinds
    assert set(get_args(NotificationKindName)) == kinds


def test__signing_route_notices__are_notification_kinds() -> None:
    assert {notice.value for notice in Notice} <= {kind.value for kind in NotificationKind}
