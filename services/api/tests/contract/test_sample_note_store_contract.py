"""Образец контрактного набора: порт заметок на InMemory и Json, плюс изоляция двух акторов."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import pytest
from hse_doc_studio.core.access.context import current_actor

from tests.contract.base import PortContract
from tests.fakes.base import ActorRequired, OwnedStore, owner_key
from tests.fixtures.actors import as_actor


class INoteStore(Protocol):
    def put(self, note_id: str, text: str) -> None: ...
    def get(self, note_id: str) -> str | None: ...
    def delete(self, note_id: str) -> bool: ...
    def ids(self) -> list[str]: ...


class InMemoryNoteStore:
    def __init__(self) -> None:
        self._store: OwnedStore[str] = OwnedStore()

    def put(self, note_id: str, text: str) -> None:
        self._store.put(note_id, text)

    def get(self, note_id: str) -> str | None:
        return self._store.get(note_id)

    def delete(self, note_id: str) -> bool:
        return self._store.delete(note_id)

    def ids(self) -> list[str]:
        return sorted(self._store.items())


class JsonNoteStore:
    """Файл на владельца, как JSON-репозитории локального режима."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self) -> Path:
        return self._root / f"{owner_key()}.json"

    def _load(self) -> dict[str, str]:
        path = self._path()
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _save(self, data: dict[str, str]) -> None:
        self._path().write_text(json.dumps(data), encoding="utf-8")

    def put(self, note_id: str, text: str) -> None:
        data = self._load()
        data[note_id] = text
        self._save(data)

    def get(self, note_id: str) -> str | None:
        return self._load().get(note_id)

    def delete(self, note_id: str) -> bool:
        data = self._load()
        existed = data.pop(note_id, None) is not None
        self._save(data)
        return existed

    def ids(self) -> list[str]:
        return sorted(self._load())


class TestNoteStoreContract(PortContract):
    implementations = {
        "in_memory": lambda tmp_path: InMemoryNoteStore(),
        "json": lambda tmp_path: JsonNoteStore(tmp_path),
    }

    def test__get__after_put__returns_text(self, port: INoteStore, two_actors) -> None:
        owner, _ = two_actors
        with as_actor(owner):
            port.put("n1", "hello")
            assert port.get("n1") == "hello"

    def test__delete__missing__returns_false(self, port: INoteStore, two_actors) -> None:
        owner, _ = two_actors
        with as_actor(owner):
            assert port.delete("nope") is False

    def test__get__other_actor__returns_none(self, port: INoteStore, two_actors) -> None:
        owner, stranger = two_actors
        with as_actor(owner):
            port.put("n1", "secret")
        with as_actor(stranger):
            assert port.get("n1") is None
            assert port.ids() == []

    def test__put__without_actor__raises(self, port: INoteStore) -> None:
        with as_actor(None), pytest.raises(ActorRequired):
            port.put("n1", "x")


def test__as_actor__restores_previous() -> None:
    before = current_actor()
    with as_actor(None):
        assert current_actor() is None
    assert current_actor() is before
