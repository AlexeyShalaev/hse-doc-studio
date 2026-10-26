from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_sync.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.git_sync.key_store import KeyFileStore

_CANARY = "ghp_CANARYtokenValue1234567890abcdef"
_AAD = "9a8b7c6d-1e2f-4a3b-8c4d-5e6f7a8b9c0d:pat"


@pytest.fixture
def key_path(tmp_path: Path) -> Path:
    return tmp_path / "secrets" / "master.keys.json"


@pytest.fixture
def cipher(key_path: Path) -> FernetSecretCipher:
    return FernetSecretCipher(KeyFileStore(key_path))


def _code(exc: pytest.ExceptionInfo[GitSyncError]) -> GitErrorCode:
    return exc.value.code


def test__encrypt_decrypt__round_trips_and_hides_the_secret(cipher: FernetSecretCipher) -> None:
    token = cipher.encrypt(Secret(_CANARY), aad=_AAD)

    assert re.fullmatch(r"hs1:k[0-9a-f]{8}:\S+", token)
    assert _CANARY not in token
    assert cipher.decrypt(token, aad=_AAD) == Secret(_CANARY)


def test__encrypt__same_secret_twice__gives_different_ciphertext(cipher: FernetSecretCipher) -> None:
    assert cipher.encrypt(Secret("a"), aad=_AAD) != cipher.encrypt(Secret("a"), aad=_AAD)


def test__encrypt_decrypt__multiline_private_key__round_trips(cipher: FernetSecretCipher) -> None:
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3Blbn\n-----END OPENSSH PRIVATE KEY-----\n"

    assert cipher.decrypt(cipher.encrypt(Secret(pem), aad=_AAD), aad=_AAD).reveal() == pem


def test__decrypt__another_records_aad__is_refused(cipher: FernetSecretCipher) -> None:
    token = cipher.encrypt(Secret(_CANARY), aad=_AAD)

    with pytest.raises(GitSyncError) as exc:
        cipher.decrypt(token, aad="11111111-1111-1111-1111-111111111111:pat")

    assert _code(exc) is GitErrorCode.secrets_unavailable


def test__decrypt__tampered_ciphertext__is_refused(cipher: FernetSecretCipher) -> None:
    token = cipher.encrypt(Secret(_CANARY), aad=_AAD)
    head, _, body = token.rpartition(":")
    flipped = body[:-4] + ("AAAA" if not body.endswith("AAAA") else "BBBB")

    with pytest.raises(GitSyncError) as exc:
        cipher.decrypt(f"{head}:{flipped}", aad=_AAD)

    assert _code(exc) is GitErrorCode.secrets_unavailable


@pytest.mark.parametrize("garbage", ["", "plain", "hs1:k1", "hs1::x", "hs2:k1:abc", "hs1:k1:not-a-token"])
def test__decrypt__malformed_envelope__is_refused(cipher: FernetSecretCipher, garbage: str) -> None:
    cipher.encrypt(Secret("x"), aad=_AAD)

    with pytest.raises(GitSyncError) as exc:
        cipher.decrypt(garbage, aad=_AAD)

    assert _code(exc) is GitErrorCode.secrets_unavailable


def test__decrypt__key_replaced_by_another__is_refused_and_unreadable(key_path: Path) -> None:
    token = FernetSecretCipher(KeyFileStore(key_path)).encrypt(Secret(_CANARY), aad=_AAD)
    data = json.loads(key_path.read_text(encoding="utf-8"))
    data["keys"][0]["fernet_key"] = Fernet.generate_key().decode()
    key_path.write_text(json.dumps(data), encoding="utf-8")
    cipher = FernetSecretCipher(KeyFileStore(key_path))

    assert cipher.can_read(token) is True  # ключ с таким идентификатором есть, но не тот
    with pytest.raises(GitSyncError) as exc:
        cipher.decrypt(token, aad=_AAD)
    assert _code(exc) is GitErrorCode.secrets_unavailable


def test__decrypt__key_file_lost__is_refused_and_does_not_create_a_new_one(key_path: Path) -> None:
    token = FernetSecretCipher(KeyFileStore(key_path)).encrypt(Secret(_CANARY), aad=_AAD)
    key_path.unlink()
    cipher = FernetSecretCipher(KeyFileStore(key_path))

    assert cipher.can_read(token) is False
    with pytest.raises(GitSyncError) as exc:
        cipher.decrypt(token, aad=_AAD)
    assert _code(exc) is GitErrorCode.secrets_unavailable
    assert not key_path.exists()


def test__rotation_ready__old_key_still_decrypts_after_a_new_primary_is_added(key_path: Path) -> None:
    old_cipher = FernetSecretCipher(KeyFileStore(key_path))
    old_token = old_cipher.encrypt(Secret(_CANARY), aad=_AAD)
    data = json.loads(key_path.read_text(encoding="utf-8"))
    data["primary"] = "k2"
    data["keys"].insert(0, {"id": "k2", "fernet_key": Fernet.generate_key().decode()})
    key_path.write_text(json.dumps(data), encoding="utf-8")
    cipher = FernetSecretCipher(KeyFileStore(key_path))

    new_token = cipher.encrypt(Secret("another"), aad=_AAD)

    assert new_token.startswith("hs1:k2:")
    assert cipher.decrypt(old_token, aad=_AAD).reveal() == _CANARY
    assert cipher.decrypt(new_token, aad=_AAD).reveal() == "another"


def test__env_key__encrypts_without_writing_a_key_file(tmp_path: Path, key_path: Path) -> None:
    cipher = FernetSecretCipher(KeyFileStore(key_path, env_key=Fernet.generate_key().decode()))

    token = cipher.encrypt(Secret(_CANARY), aad=_AAD)

    assert token.startswith("hs1:env:")
    assert cipher.decrypt(token, aad=_AAD).reveal() == _CANARY
    assert not key_path.parent.exists()
    assert list(tmp_path.iterdir()) == []


def test__env_key__other_key__cannot_read_the_ciphertext(key_path: Path) -> None:
    token = FernetSecretCipher(KeyFileStore(key_path, env_key=Fernet.generate_key().decode())).encrypt(
        Secret(_CANARY), aad=_AAD
    )
    other = FernetSecretCipher(KeyFileStore(key_path, env_key=Fernet.generate_key().decode()))

    with pytest.raises(GitSyncError):
        other.decrypt(token, aad=_AAD)


def test__error_detail__never_contains_the_secret(cipher: FernetSecretCipher) -> None:
    token = cipher.encrypt(Secret(_CANARY), aad=_AAD)

    with pytest.raises(GitSyncError) as exc:
        cipher.decrypt(token, aad="other")

    assert _CANARY not in exc.value.detail
    assert _CANARY not in repr(exc.value)
