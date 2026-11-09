"""Профиль подписанта на живом сервере: свой профиль по сессии или токену, закрытый ключ не принимается.

Путь без id пользователя, поэтому изоляция проверяется так: второй человек видит пустой профиль и не получает
картинку первого.
"""

from __future__ import annotations

import pytest

from tests.fakes.signer_profile import make_png, make_self_signed
from tests.integration.api.git_remote.conftest import Live

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

PROFILE = "/api/v1/account/signer-profile"


def certificate_and_key() -> tuple[bytes, bytes]:
    pair = make_self_signed("Анна Смирнова", serial=0xABC)
    return pair.cert_pem, pair.key_pem


def test__signer_profile__image_and_certificate__stored_for_the_owner_only(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    image = make_png(240, 80)
    cert_pem, _ = certificate_and_key()

    saved = live.call("PUT", f"{PROFILE}/image", anna, files={"file": ("sign.png", image, "image/png")})
    keyed = live.call("PUT", f"{PROFILE}/public-key", anna, files={"file": ("me.cer", cert_pem, "application/x-pem")})

    assert saved.status_code == 200, saved.text
    assert keyed.status_code == 200, keyed.text
    profile = live.call("GET", PROFILE, anna)
    assert profile.headers["cache-control"] == "no-store"
    body = profile.json()
    assert (body["image"]["width_px"], body["image"]["height_px"], body["image"]["size"]) == (240, 80, len(image))
    assert (body["public_key"]["kind"], body["public_key"]["owner"], body["public_key"]["cert_id"]) == (
        "x509",
        "Анна Смирнова",
        "ABC",
    )
    own_image = live.call("GET", f"{PROFILE}/image", anna)
    assert (own_image.status_code, own_image.content, own_image.headers["content-type"]) == (200, image, "image/png")
    assert live.call("GET", PROFILE, boris).json() == {"image": None, "public_key": None}
    assert live.call("GET", f"{PROFILE}/image", boris).status_code == 404
    actions = [row[0] for row in live.sql("SELECT action FROM audit_log WHERE actor_id = :a ORDER BY id", a=anna.id)]
    assert actions[-2:] == ["signature.profile_image", "signature.profile_key"]


def test__signer_profile__private_key_upload__400_and_profile_unchanged(live: Live) -> None:
    anna = live.person("anna")
    cert_pem, key_pem = certificate_and_key()

    response = live.call(
        "PUT", f"{PROFILE}/public-key", anna, files={"file": ("bundle.pem", cert_pem + key_pem, "application/x-pem")}
    )

    assert response.status_code == 400
    assert "закрытый ключ" in response.json()["detail"]
    assert live.call("GET", PROFILE, anna).json()["public_key"] is None
    assert live.sql("SELECT count(*) FROM signer_profiles")[0][0] == 0


def test__signer_profile__clear_both_halves__empty_profile_and_no_row(live: Live) -> None:
    anna = live.person("anna")
    live.call("PUT", f"{PROFILE}/image", anna, files={"file": ("sign.png", make_png(), "image/png")})
    live.call("PUT", f"{PROFILE}/public-key", anna, files={"file": ("me.cer", certificate_and_key()[0], "text/plain")})

    without_image = live.call("DELETE", f"{PROFILE}/image", anna)
    empty = live.call("DELETE", f"{PROFILE}/public-key", anna)

    assert without_image.json()["image"] is None
    assert without_image.json()["public_key"] is not None
    assert empty.json() == {"image": None, "public_key": None}
    assert live.call("GET", f"{PROFILE}/image", anna).status_code == 404
    assert live.sql("SELECT count(*) FROM signer_profiles")[0][0] == 0


def test__signer_profile__not_a_png__400(live: Live) -> None:
    anna = live.person("anna")

    response = live.call(
        "PUT", f"{PROFILE}/image", anna, files={"file": ("sign.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")}
    )

    assert response.status_code == 400
    assert live.call("GET", PROFILE, anna).json()["image"] is None


def test__signer_profile__without_sign_in__401(live: Live) -> None:
    assert live.call("GET", PROFILE).status_code == 401
