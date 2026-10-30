from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import structlog
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_sync.credential_repository import JsonGitCredentialRepository
from hse_doc_studio.infra.git_sync.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.git_sync.key_store import KeyFileStore

_CANARY = "ghp_CANARYtokenValue1234567890abcdef"
_NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _credential(**changes: object) -> GitCredential:
    base: dict[str, object] = {
        "id": uuid4(),
        "kind": GitCredentialKind.pat,
        "label": "Рабочий токен",
        "host": "github.com",
        "username": None,
        "status": CredentialStatus.unverified,
        "created_at": _NOW,
        "token_family": "ghp",
    }
    base.update(changes)
    return GitCredential(**base)  # type: ignore[arg-type]


@pytest.fixture
def key_path(tmp_path: Path) -> Path:
    return tmp_path / "secrets" / "master.keys.json"


@pytest.fixture
def repo(tmp_path: Path, key_path: Path) -> JsonGitCredentialRepository:
    return JsonGitCredentialRepository(tmp_path, FernetSecretCipher(KeyFileStore(key_path)))


def _unreadable(monkeypatch: pytest.MonkeyPatch, target: Path, error: OSError | None = None) -> None:
    """Чтение этого файла падает, как при блокировке клиентом синхронизации; остальное работает."""
    original = Path.read_bytes
    failure = error or PermissionError("locked")

    def read_bytes(self: Path) -> bytes:
        if self == target:
            raise failure
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)


def _file(tmp_path: Path) -> Path:
    return tmp_path / "git" / "credentials.json"


async def test__list__empty_store__is_empty_and_creates_nothing(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    assert await repo.list() == []
    assert not (tmp_path / "git").exists()


async def test__add__stores_metadata_in_clear_and_the_secret_only_encrypted(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    credential = _credential()

    await repo.add(credential, Secret(_CANARY))

    raw = _file(tmp_path).read_text(encoding="utf-8")
    assert _CANARY not in raw
    record = json.loads(raw)["credentials"][0]
    assert record["id"] == str(credential.id)
    assert record["label"] == "Рабочий токен"
    assert record["secret"].startswith("hs1:k")
    assert await repo.get(credential.id) == credential


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
async def test__add__expiry__survives_a_reload_and_an_old_record_without_it_reads_as_none(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    expiry = datetime(2027, 1, 24, tzinfo=timezone.utc)
    with_expiry = _credential(expires_at=expiry)
    legacy = _credential()
    await repo.add(with_expiry, Secret(_CANARY))
    await repo.add(legacy, Secret(_CANARY))
    path = _file(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["credentials"][1]["expires_at"]
    path.write_text(json.dumps(data), encoding="utf-8")

    assert (await repo.get(with_expiry.id)).expires_at == expiry  # type: ignore[union-attr]
    assert (await repo.get(legacy.id)).expires_at is None  # type: ignore[union-attr]


async def test__update__sets_the_expiry_without_touching_the_secret(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))
    expiry = datetime(2027, 1, 24, tzinfo=timezone.utc)

    await repo.update(replace(credential, expires_at=expiry))

    assert (await repo.get(credential.id)).expires_at == expiry  # type: ignore[union-attr]
    assert (await repo.get_secret(credential.id)).reveal() == _CANARY


async def test__add__file_is_private(repo: JsonGitCredentialRepository, tmp_path: Path) -> None:
    await repo.add(_credential(), Secret(_CANARY))

    assert stat.S_IMODE(_file(tmp_path).stat().st_mode) == 0o600
    assert stat.S_IMODE(_file(tmp_path).parent.stat().st_mode) == 0o700


async def test__get_secret__returns_what_was_stored(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))

    assert (await repo.get_secret(credential.id)).reveal() == _CANARY


async def test__get_secret__unknown_id__raises_not_found(repo: JsonGitCredentialRepository) -> None:
    with pytest.raises(NotFoundError):
        await repo.get_secret(uuid4())


async def test__list__never_decrypts(repo: JsonGitCredentialRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    await repo.add(_credential(), Secret(_CANARY))

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("list must not decrypt")

    monkeypatch.setattr(FernetSecretCipher, "decrypt", _boom)

    assert len(await repo.list()) == 1


async def test__update__without_secret__keeps_the_stored_secret(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))

    await repo.update(_credential(id=credential.id, label="Переименован"))

    assert (await repo.get(credential.id)).label == "Переименован"  # type: ignore[union-attr]
    assert (await repo.get_secret(credential.id)).reveal() == _CANARY


async def test__update__with_secret__replaces_it(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))

    await repo.update(credential, Secret("glpat-newtoken"))

    assert (await repo.get_secret(credential.id)).reveal() == "glpat-newtoken"


async def test__update__unknown_id__raises_not_found(repo: JsonGitCredentialRepository) -> None:
    with pytest.raises(NotFoundError):
        await repo.update(_credential())


async def test__delete__removes_the_record_once(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))

    assert await repo.delete(credential.id) is True
    assert await repo.delete(credential.id) is False
    assert await repo.list() == []


async def test__mark__updates_status_and_last_used_without_touching_the_secret(
    repo: JsonGitCredentialRepository,
) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))
    used = datetime(2026, 10, 27, 8, 30, tzinfo=timezone.utc)

    await repo.mark(credential.id, CredentialStatus.ok, used_at=used)

    stored = await repo.get(credential.id)
    assert stored is not None
    assert (stored.status, stored.last_used_at) == (CredentialStatus.ok, used)
    assert (await repo.get_secret(credential.id)).reveal() == _CANARY


async def test__mark__unknown_id_or_unreadable_status__is_ignored(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))

    await repo.mark(uuid4(), CredentialStatus.ok)
    await repo.mark(credential.id, CredentialStatus.unreadable)

    assert (await repo.get(credential.id)).status is CredentialStatus.unverified  # type: ignore[union-attr]


async def test__list__lost_key_file__marks_records_unreadable_without_creating_a_key(
    repo: JsonGitCredentialRepository, key_path: Path
) -> None:
    credential = _credential(status=CredentialStatus.ok)
    await repo.add(credential, Secret(_CANARY))
    key_path.unlink()

    listed = await repo.list()

    assert [c.status for c in listed] == [CredentialStatus.unreadable]
    assert not key_path.exists()
    with pytest.raises(GitSyncError) as exc:
        await repo.get_secret(credential.id)
    assert exc.value.code is GitErrorCode.secrets_unavailable


async def test__add__after_key_loss__new_record_is_readable_old_one_stays_unreadable(
    repo: JsonGitCredentialRepository, key_path: Path
) -> None:
    old = _credential()
    await repo.add(old, Secret(_CANARY))
    key_path.unlink()
    new = _credential()

    await repo.add(new, Secret("glpat-fresh"))

    statuses = {c.id: c.status for c in await repo.list()}
    assert statuses[old.id] is CredentialStatus.unreadable
    assert statuses[new.id] is CredentialStatus.unverified
    assert (await repo.get_secret(new.id)).reveal() == "glpat-fresh"


async def test__update__unreadable_record_with_new_secret__becomes_readable(
    repo: JsonGitCredentialRepository, key_path: Path
) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))
    key_path.unlink()

    await repo.update(credential, Secret("glpat-again"))

    assert (await repo.get(credential.id)).status is CredentialStatus.unverified  # type: ignore[union-attr]
    assert (await repo.get_secret(credential.id)).reveal() == "glpat-again"


async def test__get_secret__ciphertext_moved_to_another_record__is_refused(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    first, second = _credential(), _credential()
    await repo.add(first, Secret("first-secret"))
    await repo.add(second, Secret("second-secret"))
    data = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    data["credentials"][1]["secret"] = data["credentials"][0]["secret"]
    _file(tmp_path).write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(GitSyncError) as exc:
        await repo.get_secret(second.id)

    assert exc.value.code is GitErrorCode.secrets_unavailable


async def test__list__malformed_record__is_skipped_and_logged_without_its_body(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    good = _credential()
    await repo.add(good, Secret(_CANARY))
    data = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    broken_id = str(uuid4())
    data["credentials"].append({"id": broken_id, "kind": "nope", "secret": "hs1:k1:" + _CANARY})
    _file(tmp_path).write_text(json.dumps(data), encoding="utf-8")

    with structlog.testing.capture_logs() as logs:
        listed = await repo.list()

    assert [c.id for c in listed] == [good.id]
    assert broken_id in json.dumps(logs, default=str)
    assert _CANARY not in json.dumps(logs, default=str)


async def test__add__damaged_file__is_set_aside_before_writing(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    _file(tmp_path).parent.mkdir(parents=True)
    _file(tmp_path).write_text("{ damaged", encoding="utf-8")

    assert await repo.list() == []
    await repo.add(_credential(), Secret(_CANARY))

    aside = list(_file(tmp_path).parent.glob("credentials.json.corrupt-*"))
    assert len(aside) == 1
    assert aside[0].read_text(encoding="utf-8") == "{ damaged"
    assert len(await repo.list()) == 1


async def test__add__read_error__fails_and_keeps_the_saved_tokens(
    repo: JsonGitCredentialRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _credential(label="first")
    await repo.add(first, Secret(_CANARY))
    before = _file(tmp_path).read_bytes()

    with monkeypatch.context() as patch:
        _unreadable(patch, _file(tmp_path), OSError(24, "Too many open files"))
        assert await repo.list() == []
        with pytest.raises(GitSyncError) as raised:
            await repo.add(_credential(label="second"), Secret("other-secret-value"))
        with pytest.raises(GitSyncError):
            await repo.delete(first.id)

    assert raised.value.code is GitErrorCode.secrets_unavailable
    assert list(_file(tmp_path).parent.iterdir()) == [_file(tmp_path)]
    assert _file(tmp_path).read_bytes() == before
    assert [c.label for c in await repo.list()] == ["first"]
    assert (await repo.get_secret(first.id)).reveal() == _CANARY


async def test__mark__read_error_or_damaged_file__is_skipped_without_touching_the_file(
    repo: JsonGitCredentialRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credential = _credential()
    await repo.add(credential, Secret(_CANARY))
    before = _file(tmp_path).read_bytes()

    with monkeypatch.context() as patch:
        _unreadable(patch, _file(tmp_path))
        await repo.mark(credential.id, CredentialStatus.ok, used_at=_NOW)
    assert _file(tmp_path).read_bytes() == before

    _file(tmp_path).write_text("{ damaged", encoding="utf-8")
    await repo.mark(credential.id, CredentialStatus.ok, used_at=_NOW)
    assert list(_file(tmp_path).parent.iterdir()) == [_file(tmp_path)]
    assert _file(tmp_path).read_text(encoding="utf-8") == "{ damaged"


async def test__logs__never_contain_the_secret(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()

    with structlog.testing.capture_logs() as logs:
        await repo.add(credential, Secret(_CANARY))
        await repo.get_secret(credential.id)
        await repo.update(credential, Secret(_CANARY + "2"))
        await repo.mark(credential.id, CredentialStatus.ok)
        await repo.delete(credential.id)

    assert logs
    assert _CANARY not in json.dumps(logs, default=str)


async def test__ssh_key_record__keeps_public_fields_and_port(repo: JsonGitCredentialRepository) -> None:
    credential = _credential(
        kind=GitCredentialKind.ssh_key,
        token_family=None,
        username="git",
        public_key="ssh-ed25519 AAAA test",
        fingerprint_sha256="SHA256:abc",
        port=443,
    )

    await repo.add(credential, Secret("-----BEGIN OPENSSH PRIVATE KEY-----"))

    assert await repo.get(credential.id) == credential
    assert isinstance(credential.id, UUID)
