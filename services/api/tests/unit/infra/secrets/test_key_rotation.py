from __future__ import annotations

import base64
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from hse_doc_studio.api.config import Settings
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.secrets import EncryptedColumn, EncryptedColumnRegistry, column_aad
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_ring import ENV_KEY_ID, KeyRing, parse_retired_keys
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.secrets.server_keys import SecretsKeyMissingError, secrets_key_problem, server_key_store

_AAD = column_aad("git_credentials", "secret", "42")


def _cipher(tmp_path: Path, key: bytes, *retired: bytes) -> FernetSecretCipher:
    store = KeyFileStore(
        tmp_path / "k.json", env_key=key.decode(), retired_keys=",".join(item.decode() for item in retired)
    )
    return FernetSecretCipher(store)


def test__column_aad__binds_table_column_and_id() -> None:
    assert column_aad("t", "c", 7) == "t/c/7"


def test__decrypt__retired_key__opens_old_token_and_new_token_uses_primary(tmp_path: Path) -> None:
    old, new = Fernet.generate_key(), Fernet.generate_key()
    old_token = _cipher(tmp_path, old).encrypt(Secret("tok"), aad=_AAD)
    rotated = _cipher(tmp_path, new, old)

    assert rotated.decrypt(old_token, aad=_AAD).reveal() == "tok"
    assert rotated.can_read(old_token) is True
    assert rotated.is_current(old_token) is False
    fresh = rotated.encrypt(Secret("tok"), aad=_AAD)
    assert rotated.is_current(fresh) is True
    assert _cipher(tmp_path, new).decrypt(fresh, aad=_AAD).reveal() == "tok"


def test__decrypt__retired_key_dropped__is_refused(tmp_path: Path) -> None:
    old, new = Fernet.generate_key(), Fernet.generate_key()
    old_token = _cipher(tmp_path, old).encrypt(Secret("tok"), aad=_AAD)

    with pytest.raises(GitSyncError) as exc:
        _cipher(tmp_path, new).decrypt(old_token, aad=_AAD)
    assert exc.value.code is GitErrorCode.secrets_unavailable


def test__decrypt__legacy_aad__is_read_only_when_allowed(tmp_path: Path) -> None:
    cipher = _cipher(tmp_path, Fernet.generate_key())
    token = cipher.encrypt(Secret("tok"), aad="old-binding")

    assert cipher.decrypt(token, aad=_AAD, legacy_aad="old-binding").reveal() == "tok"
    with pytest.raises(GitSyncError):
        cipher.decrypt(token, aad=_AAD)


def test__key_ring__derive__is_stable_per_purpose_and_differs_from_the_key() -> None:
    key = Fernet.generate_key()
    ring = KeyRing(ENV_KEY_ID, {ENV_KEY_ID: key})

    assert ring.derive("job-token") == ring.derive("job-token")
    assert ring.derive("job-token") != ring.derive("setup-token")
    assert ring.derive("job-token") not in {key, base64.urlsafe_b64decode(key)}
    assert len(ring.derive("job-token")) == 32


def test__key_ring__derive_all__lists_primary_first_then_retired() -> None:
    old, new = Fernet.generate_key(), Fernet.generate_key()
    retired = parse_retired_keys(old.decode()) or {}
    ring = KeyRing(ENV_KEY_ID, {ENV_KEY_ID: new, **retired})

    derived = ring.derive_all("job-token")

    assert derived == [ring.derive("job-token", key=new), ring.derive("job-token", key=old)]


@pytest.mark.parametrize("raw", ["not-a-key", f"{Fernet.generate_key().decode()},bad"])
def test__retired_keys__invalid__make_the_store_unavailable(tmp_path: Path, raw: str) -> None:
    store = KeyFileStore(tmp_path / "k.json", env_key=Fernet.generate_key().decode(), retired_keys=raw)

    assert store.load() is None
    assert store.status().available is False


def test__registry__same_column_twice__is_idempotent_and_conflict_raises() -> None:
    registry = EncryptedColumnRegistry()
    registry.register(EncryptedColumn("t", "c"))
    registry.register(EncryptedColumn("t", "c"))

    assert [column.label for column in registry.all()] == ["t.c"]
    with pytest.raises(ValueError, match="уже зарегистрирована"):
        registry.register(EncryptedColumn("t", "c", pk="uid"))


def test__server_key_store__without_key__refuses_with_instructions(tmp_path: Path) -> None:
    cfg = Settings(_env_file=None, mode=StudioMode.server, data_dir=tmp_path)

    with pytest.raises(SecretsKeyMissingError, match="HSE_STUDIO__SECRETS__KEY"):
        server_key_store(cfg)
    assert not (tmp_path / "secrets").exists()


def test__server_key_store__invalid_key__refuses(tmp_path: Path) -> None:
    cfg = Settings(_env_file=None, mode=StudioMode.server, data_dir=tmp_path, secrets={"key": "nope"})

    assert secrets_key_problem(cfg) is not None


def test__server_key_store__valid_key__is_env_only(tmp_path: Path) -> None:
    cfg = Settings(
        _env_file=None, mode=StudioMode.server, data_dir=tmp_path, secrets={"key": Fernet.generate_key().decode()}
    )

    store = server_key_store(cfg)

    assert secrets_key_problem(cfg) is None
    assert store.ensure_primary().primary_id == ENV_KEY_ID
    assert not (tmp_path / "secrets").exists()
