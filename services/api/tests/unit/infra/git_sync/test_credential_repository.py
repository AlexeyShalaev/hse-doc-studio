from __future__ import annotations

import json
import os
import stat
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


def _file(tmp_path: Path) -> Path:
    return tmp_path / "git" / "credentials.json"


def test__list__empty_store__is_empty_and_creates_nothing(repo: JsonGitCredentialRepository, tmp_path: Path) -> None:
    assert repo.list() == []
    assert not (tmp_path / "git").exists()


def test__add__stores_metadata_in_clear_and_the_secret_only_encrypted(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    credential = _credential()

    repo.add(credential, Secret(_CANARY))

    raw = _file(tmp_path).read_text(encoding="utf-8")
    assert _CANARY not in raw
    record = json.loads(raw)["credentials"][0]
    assert record["id"] == str(credential.id)
    assert record["label"] == "Рабочий токен"
    assert record["secret"].startswith("hs1:k")
    assert repo.get(credential.id) == credential


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test__add__file_is_private(repo: JsonGitCredentialRepository, tmp_path: Path) -> None:
    repo.add(_credential(), Secret(_CANARY))

    assert stat.S_IMODE(_file(tmp_path).stat().st_mode) == 0o600
    assert stat.S_IMODE(_file(tmp_path).parent.stat().st_mode) == 0o700


def test__get_secret__returns_what_was_stored(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    repo.add(credential, Secret(_CANARY))

    assert repo.get_secret(credential.id).reveal() == _CANARY


def test__get_secret__unknown_id__raises_not_found(repo: JsonGitCredentialRepository) -> None:
    with pytest.raises(NotFoundError):
        repo.get_secret(uuid4())


def test__list__never_decrypts(repo: JsonGitCredentialRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    repo.add(_credential(), Secret(_CANARY))

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("list must not decrypt")

    monkeypatch.setattr(FernetSecretCipher, "decrypt", _boom)

    assert len(repo.list()) == 1


def test__update__without_secret__keeps_the_stored_secret(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    repo.add(credential, Secret(_CANARY))

    repo.update(_credential(id=credential.id, label="Переименован"))

    assert repo.get(credential.id).label == "Переименован"  # type: ignore[union-attr]
    assert repo.get_secret(credential.id).reveal() == _CANARY


def test__update__with_secret__replaces_it(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    repo.add(credential, Secret(_CANARY))

    repo.update(credential, Secret("glpat-newtoken"))

    assert repo.get_secret(credential.id).reveal() == "glpat-newtoken"


def test__update__unknown_id__raises_not_found(repo: JsonGitCredentialRepository) -> None:
    with pytest.raises(NotFoundError):
        repo.update(_credential())


def test__delete__removes_the_record_once(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    repo.add(credential, Secret(_CANARY))

    assert repo.delete(credential.id) is True
    assert repo.delete(credential.id) is False
    assert repo.list() == []


def test__mark__updates_status_and_last_used_without_touching_the_secret(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    repo.add(credential, Secret(_CANARY))
    used = datetime(2026, 10, 27, 8, 30, tzinfo=timezone.utc)

    repo.mark(credential.id, CredentialStatus.ok, used_at=used)

    stored = repo.get(credential.id)
    assert stored is not None
    assert (stored.status, stored.last_used_at) == (CredentialStatus.ok, used)
    assert repo.get_secret(credential.id).reveal() == _CANARY


def test__mark__unknown_id_or_unreadable_status__is_ignored(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()
    repo.add(credential, Secret(_CANARY))

    repo.mark(uuid4(), CredentialStatus.ok)
    repo.mark(credential.id, CredentialStatus.unreadable)

    assert repo.get(credential.id).status is CredentialStatus.unverified  # type: ignore[union-attr]


def test__list__lost_key_file__marks_records_unreadable_without_creating_a_key(
    repo: JsonGitCredentialRepository, key_path: Path
) -> None:
    credential = _credential(status=CredentialStatus.ok)
    repo.add(credential, Secret(_CANARY))
    key_path.unlink()

    listed = repo.list()

    assert [c.status for c in listed] == [CredentialStatus.unreadable]
    assert not key_path.exists()
    with pytest.raises(GitSyncError) as exc:
        repo.get_secret(credential.id)
    assert exc.value.code is GitErrorCode.secrets_unavailable


def test__add__after_key_loss__new_record_is_readable_old_one_stays_unreadable(
    repo: JsonGitCredentialRepository, key_path: Path
) -> None:
    old = _credential()
    repo.add(old, Secret(_CANARY))
    key_path.unlink()
    new = _credential()

    repo.add(new, Secret("glpat-fresh"))

    statuses = {c.id: c.status for c in repo.list()}
    assert statuses[old.id] is CredentialStatus.unreadable
    assert statuses[new.id] is CredentialStatus.unverified
    assert repo.get_secret(new.id).reveal() == "glpat-fresh"


def test__update__unreadable_record_with_new_secret__becomes_readable(
    repo: JsonGitCredentialRepository, key_path: Path
) -> None:
    credential = _credential()
    repo.add(credential, Secret(_CANARY))
    key_path.unlink()

    repo.update(credential, Secret("glpat-again"))

    assert repo.get(credential.id).status is CredentialStatus.unverified  # type: ignore[union-attr]
    assert repo.get_secret(credential.id).reveal() == "glpat-again"


def test__get_secret__ciphertext_moved_to_another_record__is_refused(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    first, second = _credential(), _credential()
    repo.add(first, Secret("first-secret"))
    repo.add(second, Secret("second-secret"))
    data = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    data["credentials"][1]["secret"] = data["credentials"][0]["secret"]
    _file(tmp_path).write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(GitSyncError) as exc:
        repo.get_secret(second.id)

    assert exc.value.code is GitErrorCode.secrets_unavailable


def test__list__malformed_record__is_skipped_and_logged_without_its_body(
    repo: JsonGitCredentialRepository, tmp_path: Path
) -> None:
    good = _credential()
    repo.add(good, Secret(_CANARY))
    data = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    broken_id = str(uuid4())
    data["credentials"].append({"id": broken_id, "kind": "nope", "secret": "hs1:k1:" + _CANARY})
    _file(tmp_path).write_text(json.dumps(data), encoding="utf-8")

    with structlog.testing.capture_logs() as logs:
        listed = repo.list()

    assert [c.id for c in listed] == [good.id]
    assert broken_id in json.dumps(logs, default=str)
    assert _CANARY not in json.dumps(logs, default=str)


def test__add__damaged_file__is_set_aside_before_writing(repo: JsonGitCredentialRepository, tmp_path: Path) -> None:
    _file(tmp_path).parent.mkdir(parents=True)
    _file(tmp_path).write_text("{ damaged", encoding="utf-8")

    assert repo.list() == []
    repo.add(_credential(), Secret(_CANARY))

    aside = list(_file(tmp_path).parent.glob("credentials.json.corrupt-*"))
    assert len(aside) == 1
    assert aside[0].read_text(encoding="utf-8") == "{ damaged"
    assert len(repo.list()) == 1


def test__logs__never_contain_the_secret(repo: JsonGitCredentialRepository) -> None:
    credential = _credential()

    with structlog.testing.capture_logs() as logs:
        repo.add(credential, Secret(_CANARY))
        repo.get_secret(credential.id)
        repo.update(credential, Secret(_CANARY + "2"))
        repo.mark(credential.id, CredentialStatus.ok)
        repo.delete(credential.id)

    assert logs
    assert _CANARY not in json.dumps(logs, default=str)


def test__ssh_key_record__keeps_public_fields_and_port(repo: JsonGitCredentialRepository) -> None:
    credential = _credential(
        kind=GitCredentialKind.ssh_key,
        token_family=None,
        username="git",
        public_key="ssh-ed25519 AAAA test",
        fingerprint_sha256="SHA256:abc",
        port=443,
    )

    repo.add(credential, Secret("-----BEGIN OPENSSH PRIVATE KEY-----"))

    assert repo.get(credential.id) == credential
    assert isinstance(credential.id, UUID)
