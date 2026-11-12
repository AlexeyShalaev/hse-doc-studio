"""Журнал аудита маршрута подписания и словарь админки: у каждого действия есть подпись на обоих языках.

Раздел «Аудит» показывает действие по ключу `audit.actions.<действие с подчёркиваниями>` (web-app,
`features/admin-users/lib/auditLabel.ts`); без подписи на экран вышел бы сырой код события.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hse_doc_studio.core.signing_route.audit import RouteAuditAction
from hse_doc_studio.core.signing_route.entities import StopReason

_REPO = Path(__file__).resolve().parents[5]
_LOCALES = _REPO / "services" / "web-app" / "src" / "shared" / "lib" / "i18n" / "locales"
# Записи подписей, которые маршрут помечает своим `route_id` (docs/design/signing-route.md, 6.7).
# «Показать» придержанную маршрутом картинку (5.6): картинка встаёт без согласия подписанта, это видно в журнале.
_SIGNATURE_ACTIONS = (
    "signature.freeze",
    "signature.sign",
    "signature.attach",
    "signature.profile_image",
    "signature.release",
    # «Подпись необязательна» на точке (13.8): с `route_id`, если документ держит маршрут.
    "signature.optional",
)


def _audit(lng: str) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = json.loads((_LOCALES / lng / "admin" / "audit.json").read_text("utf-8"))["audit"]
    return found


@pytest.mark.parametrize("lng", ["ru", "en"])
def test__audit_dictionary__every_signing_route_action_has_a_label(lng: str) -> None:
    labels = _audit(lng)["actions"]
    actions = [*(a.value for a in RouteAuditAction), *_SIGNATURE_ACTIONS]

    missing = [action for action in actions if not labels.get(action.replace(".", "_"), "").strip()]

    assert not missing


@pytest.mark.parametrize("lng", ["ru", "en"])
def test__audit_dictionary__stop_reasons_and_route_fields_are_readable(lng: str) -> None:
    audit = _audit(lng)

    assert not [reason.value for reason in StopReason if reason.value not in audit["values"]]
    assert not [
        key
        for key in ("route_id", "profile_id", "round", "step", "persona", "optional")
        if key not in audit["detailKeys"]
    ]
