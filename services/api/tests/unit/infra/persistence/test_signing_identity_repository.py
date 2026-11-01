"""JsonSigningIdentityRepository: прежняя раскладка signing_keys/<id>/, сессия ключа отдаёт её без копирования."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from hse_doc_studio.core.entities import SigningIdentity, SigningKeyMaterial
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.infra.persistence.signing_identity import JsonSigningIdentityRepository

_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _identity() -> SigningIdentity:
    return SigningIdentity(
        id=uuid4(),
        label="Моя",
        kind=SigningIdentityKind.self_signed,
        subject_cn="Иван",
        not_after=_NOW,
        trusted=False,
        created_at=_NOW,
    )


async def test__create_with_material__writes_keys_into_data_dir_and_session_returns_that_folder(tmp_path: Path) -> None:
    repo = JsonSigningIdentityRepository(tmp_path)
    identity = _identity()

    await repo.create(identity, SigningKeyMaterial(key_pem=b"KEY", cert_pem=b"CERT"))

    expected = tmp_path / "signing_keys" / str(identity.id)
    assert (expected / "key.pem").read_bytes() == b"KEY"
    assert await repo.read_cert(identity.id) == b"CERT"
    async with repo.private_key_session(identity.id) as directory:
        assert directory == expected
    assert expected.exists()


async def test__delete__removes_record_and_key_folder(tmp_path: Path) -> None:
    repo = JsonSigningIdentityRepository(tmp_path)
    identity = _identity()
    await repo.create(identity, SigningKeyMaterial(key_pem=b"KEY", cert_pem=b"CERT"))

    assert await repo.delete(identity.id) is True

    assert await repo.get(identity.id) is None
    assert not (tmp_path / "signing_keys" / str(identity.id)).exists()
    assert await repo.read_cert(identity.id) is None
    assert await repo.delete(identity.id) is False
