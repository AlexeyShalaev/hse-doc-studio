"""Запрет админа на ключи на сервере блокирует подпись уже сохранёнными ключами Студии, локально не действует."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.signatures.key_policy import LocalSigningKeyPolicy, SigningKeyStorageDeniedError
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.signatures._studio_signer import StudioSigner

pytestmark = pytest.mark.unit

_EMPTY = SignaturesState(slots={}, placements={})


class _Denied:
    async def server_key_storage_allowed(self) -> bool:
        return False


def _signer(policy: Any) -> StudioSigner:
    unused = cast(Any, None)
    return StudioSigner(unused, unused, unused, unused, unused, unused, unused, policy)


def _identity(kind: SigningIdentityKind) -> SigningIdentity:
    now = datetime.now(UTC)
    return SigningIdentity(
        id=uuid4(), label="Ключ", kind=kind, subject_cn="Иван", not_after=now, trusted=False, created_at=now
    )


@pytest.mark.parametrize("kind", [SigningIdentityKind.openpgp, SigningIdentityKind.pkcs12])
async def test__sign_detached__storage_forbidden__refused_before_the_key_is_touched(kind: SigningIdentityKind) -> None:
    signer = _signer(_Denied())

    with pytest.raises(SigningKeyStorageDeniedError):
        await signer.sign_detached(cast(Any, None), _EMPTY, cast(Any, None), "author", _identity(kind), "")


async def test__sign_pades__storage_forbidden__refused() -> None:
    signer = _signer(_Denied())

    with pytest.raises(SigningKeyStorageDeniedError):
        await signer.sign_pades(
            cast(Any, None), _EMPTY, cast(Any, None), "author", _identity(SigningIdentityKind.pkcs12)
        )


async def test__require_key_allowed__local_policy__passes() -> None:
    await _signer(LocalSigningKeyPolicy()).require_key_allowed()
