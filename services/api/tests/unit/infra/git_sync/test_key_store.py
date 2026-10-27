from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import KeySource
from hse_doc_studio.infra.git_sync.key_store import ENV_KEY_ID, KeyFileStore

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


@pytest.fixture
def key_path(tmp_path: Path) -> Path:
    return tmp_path / "secrets" / "master.keys.json"


def _unreadable(monkeypatch: pytest.MonkeyPatch, target: Path, error: OSError | None = None) -> None:
    """Чтение этого файла падает, как при блокировке клиентом синхронизации; остальное работает."""
    original = Path.read_bytes
    failure = error or PermissionError("locked")

    def read_bytes(self: Path) -> bytes:
        if self == target:
            raise failure
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)


def test__load__no_file__is_none_and_creates_nothing(key_path: Path) -> None:
    store = KeyFileStore(key_path)

    assert store.load() is None
    assert not key_path.exists()
    assert not key_path.parent.exists()


def test__status__no_file__is_available_because_the_key_is_created_lazily(key_path: Path) -> None:
    status = KeyFileStore(key_path).status()

    assert status.source is KeySource.file
    assert status.available is True


def test__ensure_primary__no_file__creates_a_valid_key_file(key_path: Path) -> None:
    store = KeyFileStore(key_path)

    ring = store.ensure_primary()

    assert re.fullmatch(r"k[0-9a-f]{8}", ring.primary_id)
    data = json.loads(key_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["primary"] == ring.primary_id
    Fernet(data["keys"][0]["fernet_key"].encode())
    assert store.load() == ring


def test__ensure_primary__second_call__keeps_the_same_key(key_path: Path) -> None:
    store = KeyFileStore(key_path)

    first = store.ensure_primary()
    second = KeyFileStore(key_path).ensure_primary()

    assert first == second


@posix_only
def test__ensure_primary__creates_private_file_and_directory(key_path: Path) -> None:
    store = KeyFileStore(key_path)

    store.ensure_primary()

    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(key_path.parent.stat().st_mode) == 0o700
    assert store.status().permissions_enforced is True


@posix_only
def test__status__file_with_open_permissions__reports_not_enforced(key_path: Path) -> None:
    store = KeyFileStore(key_path)
    store.ensure_primary()
    key_path.chmod(0o644)

    assert store.status().permissions_enforced is False


def test__ensure_primary__corrupt_file__is_set_aside_not_overwritten(key_path: Path) -> None:
    key_path.parent.mkdir(parents=True)
    key_path.write_text("{ not json", encoding="utf-8")
    store = KeyFileStore(key_path)

    assert store.load() is None
    assert store.status().available is False
    ring = store.ensure_primary()

    aside = list(key_path.parent.glob("master.keys.json.corrupt-*"))
    assert len(aside) == 1
    assert aside[0].read_text(encoding="utf-8") == "{ not json"
    assert store.load() == ring
    assert store.status().available is True


def test__ensure_primary__another_process_created_the_key_first__its_key_wins(key_path: Path) -> None:
    # Два процесса увидели «файла нет»: второй не должен затереть ключ первого, иначе токены под ним потеряны.
    slow = KeyFileStore(key_path)
    other_ring = KeyFileStore(key_path).ensure_primary()
    seen_missing = iter([(None, "missing")])
    real_read = slow._read_file
    slow._read_file = lambda: next(seen_missing, None) or real_read()  # type: ignore[method-assign]

    ring = slow.ensure_primary()

    assert ring == other_ring
    assert KeyFileStore(key_path).load() == other_ring
    assert list(key_path.parent.iterdir()) == [key_path]


def test__ensure_primary__read_error__keeps_the_file_and_does_not_create_a_new_key(
    key_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ring = KeyFileStore(key_path).ensure_primary()
    before = key_path.read_bytes()
    store = KeyFileStore(key_path)

    with monkeypatch.context() as patch:
        _unreadable(patch, key_path)
        assert store.load() is None
        assert store.status().available is False
        with pytest.raises(GitSyncError) as raised:
            store.ensure_primary()

    assert raised.value.code is GitErrorCode.secrets_unavailable
    assert list(key_path.parent.iterdir()) == [key_path]
    assert key_path.read_bytes() == before
    assert store.load() == ring


def test__ensure_primary__inaccessible_directory__is_unavailable_not_a_crash(
    key_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def exists(self: Path) -> bool:
        raise PermissionError("no access")

    monkeypatch.setattr(Path, "exists", exists)
    store = KeyFileStore(key_path)

    assert store.load() is None
    assert store.status().available is False
    with pytest.raises(GitSyncError) as raised:
        store.ensure_primary()
    assert raised.value.code is GitErrorCode.secrets_unavailable


def test__ensure_primary__file_not_utf8__is_corrupt_and_set_aside(key_path: Path) -> None:
    key_path.parent.mkdir(parents=True)
    key_path.write_bytes(b"\xff\xfe\x00garbage")
    store = KeyFileStore(key_path)

    assert store.status().available is False
    store.ensure_primary()

    assert len(list(key_path.parent.glob("master.keys.json.corrupt-*"))) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 2, "primary": "k1", "keys": []},
        {"version": 1, "primary": "k9", "keys": [{"id": "k1", "fernet_key": Fernet.generate_key().decode()}]},
        {"version": 1, "primary": "k1", "keys": [{"id": "k1", "fernet_key": "short"}]},
        {"version": 1, "primary": "k1", "keys": [{"id": "bad id!", "fernet_key": Fernet.generate_key().decode()}]},
        [1, 2],
    ],
)
def test__load__invalid_structure__is_treated_as_corrupt(key_path: Path, payload: object) -> None:
    key_path.parent.mkdir(parents=True)
    key_path.write_text(json.dumps(payload), encoding="utf-8")
    store = KeyFileStore(key_path)

    assert store.load() is None
    assert store.status().available is False


def test__load__several_keys__reads_all_and_primary(key_path: Path) -> None:
    old, new = Fernet.generate_key(), Fernet.generate_key()
    key_path.parent.mkdir(parents=True)
    key_path.write_text(
        json.dumps(
            {
                "version": 1,
                "primary": "k2",
                "keys": [{"id": "k2", "fernet_key": new.decode()}, {"id": "k1", "fernet_key": old.decode()}],
            }
        ),
        encoding="utf-8",
    )

    ring = KeyFileStore(key_path).load()

    assert ring is not None
    assert ring.primary_id == "k2"
    assert ring.keys == {"k1": old, "k2": new}


def test__env_key__is_used_and_never_written(key_path: Path) -> None:
    key = Fernet.generate_key().decode()
    store = KeyFileStore(key_path, env_key=key)

    ring = store.ensure_primary()

    assert store.source is KeySource.env
    assert ring.primary_id == ENV_KEY_ID
    assert ring.keys[ENV_KEY_ID] == key.encode()
    assert not key_path.parent.exists()
    assert store.status().available is True


def test__env_key_file__is_read_and_never_written(tmp_path: Path, key_path: Path) -> None:
    key = Fernet.generate_key()
    key_file = tmp_path / "docker-secret"
    key_file.write_bytes(key + b"\n")
    store = KeyFileStore(key_path, env_key_file=key_file)

    ring = store.ensure_primary()

    assert ring.keys[ENV_KEY_ID] == key
    assert not key_path.parent.exists()


@pytest.mark.parametrize("env_key", ["", "not-a-fernet-key"])
def test__env_key__invalid__is_unavailable_and_refuses_to_write(key_path: Path, env_key: str) -> None:
    store = KeyFileStore(key_path, env_key=env_key or None, env_key_file=None if env_key else key_path.parent / "nope")

    assert store.load() is None
    assert store.status().available is False
    with pytest.raises(GitSyncError) as exc:
        store.ensure_primary()
    assert exc.value.code is GitErrorCode.secrets_unavailable
    assert not key_path.parent.exists()
