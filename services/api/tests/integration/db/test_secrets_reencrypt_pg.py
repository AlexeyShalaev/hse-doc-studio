from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.secrets import EncryptedColumn, EncryptedColumnRegistry, column_aad
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.secrets.reencrypt import reencrypt_all
from sqlalchemy import text

pytestmark = pytest.mark.pg

_COLUMN = EncryptedColumn("enc_probe", "secret", legacy_aad=lambda row_id: f"old:{row_id}")


def _cipher(tmp_path: Path, key: bytes, *retired: bytes) -> FernetSecretCipher:
    return FernetSecretCipher(
        KeyFileStore(tmp_path / "k.json", env_key=key.decode(), retired_keys=",".join(k.decode() for k in retired))
    )


async def _read(engine, cipher: FernetSecretCipher) -> list[str]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, secret FROM enc_probe WHERE secret IS NOT NULL ORDER BY id"))).all()
    return [cipher.decrypt(token, aad=column_aad("enc_probe", "secret", pk)).reveal() for pk, token in rows]


async def test__reencrypt__moves_retired_and_legacy_rows_to_the_primary_key(pg_db_factory, tmp_path: Path) -> None:
    engine = await pg_db_factory()
    old, new = Fernet.generate_key(), Fernet.generate_key()
    old_cipher = _cipher(tmp_path, old)
    registry = EncryptedColumnRegistry()
    registry.register(_COLUMN)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE enc_probe (id integer PRIMARY KEY, secret text)"))
        for pk, aad in ((1, column_aad("enc_probe", "secret", 1)), (2, "old:2")):
            sealed = old_cipher.encrypt(Secret(f"v{pk}"), aad=aad)
            await conn.execute(text("INSERT INTO enc_probe VALUES (:id, :s)"), {"id": pk, "s": sealed})
        await conn.execute(text("INSERT INTO enc_probe VALUES (3, NULL)"))
    rotated = _cipher(tmp_path, new, old)

    dry = await reencrypt_all(engine, rotated, registry, dry_run=True)
    done = await reencrypt_all(engine, rotated, registry)
    again = await reencrypt_all(engine, rotated, registry)

    assert (dry.updated, done.updated, done.ok) == (2, 2, True)
    assert (again.updated, again.current) == (0, 2)
    assert await _read(engine, _cipher(tmp_path, new)) == ["v1", "v2"]


async def test__reencrypt__unreadable_row__is_reported_and_left_untouched(pg_db_factory, tmp_path: Path) -> None:
    engine = await pg_db_factory()
    registry = EncryptedColumnRegistry()
    registry.register(_COLUMN)
    lost = _cipher(tmp_path, Fernet.generate_key()).encrypt(Secret("x"), aad=column_aad("enc_probe", "secret", 1))
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE enc_probe (id integer PRIMARY KEY, secret text)"))
        await conn.execute(text("INSERT INTO enc_probe VALUES (1, :s)"), {"s": lost})

    report = await reencrypt_all(engine, _cipher(tmp_path, Fernet.generate_key()), registry)

    assert report.unreadable == ["enc_probe.secret#1"]
    assert report.ok is False
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT secret FROM enc_probe"))).scalar_one() == lost
