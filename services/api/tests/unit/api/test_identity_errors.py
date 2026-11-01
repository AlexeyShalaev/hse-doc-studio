from __future__ import annotations

from hse_doc_studio.api.identity_errors import IDENTITY_ERROR_STATUS, identity_error_body
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode


def test_status_table_covers_every_code() -> None:
    assert set(IDENTITY_ERROR_STATUS) == set(IdentityErrorCode)


def test_auth_required_is_401_and_csrf_is_403() -> None:
    assert IDENTITY_ERROR_STATUS[IdentityErrorCode.auth_required] == 401
    assert IDENTITY_ERROR_STATUS[IdentityErrorCode.csrf_failed] == 403
    assert IDENTITY_ERROR_STATUS[IdentityErrorCode.rate_limited] == 429


def test_body_carries_detail_and_code() -> None:
    body = identity_error_body(IdentityError(IdentityErrorCode.auth_required, "Нужно войти."))

    assert body == {"detail": "Нужно войти.", "code": "auth_required"}
