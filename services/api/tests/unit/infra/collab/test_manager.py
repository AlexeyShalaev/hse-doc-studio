"""Комнаты совместной правки на pycrdt: сходимость двух клиентов, чтение без записи, диск и слияние, пределы."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.api.config.collab import CollabConfig
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.collab.awareness import AwarenessEntry, decode_awareness, encode_awareness, write_uint
from hse_doc_studio.core.collab.ports import TextSnapshot
from hse_doc_studio.infra.collab import protocol as proto
from hse_doc_studio.infra.collab.manager import (
    CLOSE_BUSY,
    IN_COLLAB_PERSIST,
    Client,
    CollabIdentity,
    CollabManager,
    CollabRefusedError,
    Room,
)
from hse_doc_studio.infra.collab.state_store import YStateStore
from pycrdt import Doc, Text, create_sync_message, create_update_message, handle_sync_message

PATH = "main.tex"
del Actor


def _etag(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


class FakeStore:
    """Файл в памяти; `external` имитирует чужую запись (git, VS Code)."""

    def __init__(self, text: str) -> None:
        self.text: str | None = text
        self.writes: list[str] = []
        self.recorded = 0
        self.in_persist_on_write: list[bool] = []

    async def read(self, project_id: object, path: str) -> TextSnapshot | None:
        return None if self.text is None else TextSnapshot(self.text, _etag(self.text))

    async def etag(self, project_id: object, path: str) -> str | None:
        return None if self.text is None else _etag(self.text)

    async def write(self, project_id: object, path: str, text: str) -> str:
        self.in_persist_on_write.append(IN_COLLAB_PERSIST.get())
        self.text = text
        self.writes.append(text)
        return _etag(text)

    async def record_external(self, project_id: object, path: str) -> None:
        self.recorded += 1

    async def folder(self, project_id: object) -> Path | None:
        return Path("/srv/projects/p1")


class FakeConn:
    def __init__(self) -> None:
        self.closed: tuple[int, str] | None = None

    async def send_bytes(self, data: bytes) -> None: ...

    async def close(self, code: int, reason: str) -> None:
        self.closed = (code, reason)


class Browser:
    """Клиент-браузер: настоящий Y.Doc и очередь кадров сервера, применяемая по требованию."""

    def __init__(self, room: Room, client: Client) -> None:
        self.room = room
        self.client = client
        self.doc = Doc()
        self.text: Text = self.doc.get("text", type=Text)
        self.events: list[dict[str, object]] = []
        self.awareness: list[AwarenessEntry] = []
        self._sv = self.doc.get_state()

    async def pump(self) -> None:
        while not self.client.outbox.empty():
            frame = self.client.outbox.get_nowait()
            if not frame:
                continue
            if frame[0] == proto.MSG_SYNC:
                reply = handle_sync_message(frame[1:], self.doc)
                if reply is not None:
                    await self.room.receive(self.client, reply)
            elif frame[0] == proto.MSG_EVENT:
                self.events.append(json.loads(frame[1:]))
            elif frame[0] == proto.MSG_AWARENESS:
                self.awareness.extend(decode_awareness(proto.message_body(frame[1:])))

    async def hello(self) -> None:
        await self.room.receive(self.client, create_sync_message(self.doc))
        await self.pump()
        self._sv = self.doc.get_state()

    async def type_at(self, index: int, value: str) -> None:
        before = self.doc.get_state()
        self.text.insert(index, value)
        await self.room.receive(self.client, create_update_message(self.doc.get_update(before)))

    def event_types(self) -> list[object]:
        return [e["type"] for e in self.events]


def _cfg(**over: object) -> CollabConfig:
    base = {"persist_delay_s": 0.05, "persist_max_wait_s": 0.5, "poll_interval_s": 0.05, "idle_ttl_s": 0.05}
    return CollabConfig(**{**base, **over})


@pytest.fixture
def store() -> FakeStore:
    return FakeStore("Первая строка\nВторая строка\n")


@pytest.fixture
def manager(store: FakeStore, tmp_path: Path) -> CollabManager:
    return CollabManager(store, YStateStore(tmp_path / "collab"), _cfg())  # type: ignore[arg-type]


async def _join(manager: CollabManager, project: object, who: str, *, can_write: bool = True) -> Browser:
    room, client = await manager.join(project, PATH, FakeConn(), CollabIdentity(who, who.title(), can_write))  # type: ignore[arg-type]
    browser = Browser(room, client)
    await browser.pump()
    await browser.hello()
    return browser


async def _settle(seconds: float = 0.3) -> None:
    await asyncio.sleep(seconds)


async def test__two_writers__converge_and_file_gets_merged_text(manager: CollabManager, store: FakeStore) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    boris = await _join(manager, project, "boris")
    assert str(anna.text) == "Первая строка\nВторая строка\n" == str(boris.text)

    await anna.type_at(0, "А: ")
    await boris.type_at(len(str(boris.text).encode()), "Б: конец\n")
    await anna.pump()
    await boris.pump()
    await _settle()

    assert str(anna.text) == str(boris.text)
    assert store.text == "А: Первая строка\nВторая строка\nБ: конец\n"
    assert all(store.in_persist_on_write)


async def test__reader__cannot_write_and_is_told_once(manager: CollabManager, store: FakeStore) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    reader = await _join(manager, project, "gleb", can_write=False)

    await reader.type_at(0, "ВЗЛОМ ")
    await reader.type_at(0, "ЕЩЁ ")
    await reader.pump()
    await anna.pump()
    await _settle()

    assert str(anna.text) == "Первая строка\nВторая строка\n"
    assert store.text == "Первая строка\nВторая строка\n"
    assert reader.event_types().count("read_only") == 1


async def test__reader__sees_live_changes(manager: CollabManager) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    reader = await _join(manager, project, "gleb", can_write=False)

    await anna.type_at(0, "Новое ")
    await reader.pump()

    assert str(reader.text).startswith("Новое Первая")


async def test__external_change__is_applied_as_operations_without_losing_open_edits(
    manager: CollabManager, store: FakeStore
) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")

    store.text = "Первая строка\nВторая строка\nТретья из git\n"
    await _settle()
    await anna.pump()

    assert str(anna.text) == "Первая строка\nВторая строка\nТретья из git\n"
    assert "external" in anna.event_types()
    assert store.writes == []


async def test__external_change_while_typing__is_merged_threeway(manager: CollabManager, store: FakeStore) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    room = anna.room
    await anna.type_at(0, "Моя правка. ")
    # Чужая запись приходит до того, как комната успела сохранить набранное.
    store.text = "Первая строка\nВторая строка\nДобавлено снаружи\n"

    assert await room.persist(force=True)

    assert store.text == "Моя правка. Первая строка\nВторая строка\nДобавлено снаружи\n"
    assert store.recorded == 0


async def test__conflicting_external_change__records_foreign_version_in_history(
    manager: CollabManager, store: FakeStore
) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    await anna.type_at(0, "Моя ")
    store.text = "Чужая первая строка\nВторая строка\n"

    await anna.room.persist(force=True)

    assert store.recorded == 1
    assert store.text.startswith("Моя Первая строка")


async def test__flush_folder__writes_dirty_rooms_before_folder_operation(
    manager: CollabManager, store: FakeStore
) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    await anna.type_at(0, "Срочно ")
    assert store.writes == []

    await manager.flush_folder(Path("/srv/projects/p1"))

    assert store.text is not None
    assert store.text.startswith("Срочно ")


async def test__flush_inside_persist_is_noop(manager: CollabManager) -> None:
    token = IN_COLLAB_PERSIST.set(True)
    try:
        await asyncio.wait_for(manager.flush_folder(Path("/srv/projects/p1")), 1)
    finally:
        IN_COLLAB_PERSIST.reset(token)


async def test__cyrillic_and_emoji__external_edit_lands_on_right_offsets(
    manager: CollabManager, store: FakeStore
) -> None:
    store.text = "Привет 😀 мир\nстрока два\n"
    project = uuid4()
    anna = await _join(manager, project, "anna")

    store.text = "Привет 😀 большой мир\nстрока два!\n"
    await _settle()
    await anna.pump()

    assert str(anna.text) == "Привет 😀 большой мир\nстрока два!\n"


async def test__file_deleted__room_closes_and_clients_are_told(manager: CollabManager, store: FakeStore) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")

    store.text = None
    await _settle()
    await anna.pump()

    assert {"type": "error", "code": "file_gone"} in anna.events
    assert manager.room_count() == 0


async def test__not_text_file__is_refused(manager: CollabManager, store: FakeStore) -> None:
    store.text = None

    with pytest.raises(CollabRefusedError) as refused:
        await manager.join(uuid4(), PATH, FakeConn(), CollabIdentity("anna", "Анна", True))  # type: ignore[arg-type]

    assert refused.value.reason == "not_text"


async def test__limits__room_full_and_user_connections(tmp_path: Path, store: FakeStore) -> None:
    manager = CollabManager(
        store,  # type: ignore[arg-type]
        YStateStore(tmp_path),
        _cfg(max_clients_per_room=2, max_connections_per_user=1, max_rooms_per_project=1),
    )
    project = uuid4()
    await _join(manager, project, "anna")
    with pytest.raises(CollabRefusedError) as same_user:
        await _join(manager, project, "anna")
    await _join(manager, project, "boris")
    with pytest.raises(CollabRefusedError) as full:
        await _join(manager, project, "vera")
    with pytest.raises(CollabRefusedError) as other_file:
        await manager.join(project, "other.tex", FakeConn(), CollabIdentity("dina", "Дина", True))  # type: ignore[arg-type]

    assert {same_user.value.code, full.value.code, other_file.value.code} == {CLOSE_BUSY}
    assert full.value.reason == "room_full"
    assert other_file.value.reason == "project_busy"


async def test__room_survives_restart_with_same_lineage(store: FakeStore, tmp_path: Path) -> None:
    first = CollabManager(store, YStateStore(tmp_path), _cfg())  # type: ignore[arg-type]
    project = uuid4()
    anna = await _join(first, project, "anna")
    epoch = anna.room.epoch
    await anna.type_at(0, "До перезапуска. ")
    await anna.room.persist(force=True)
    await first.shutdown()

    second = CollabManager(store, YStateStore(tmp_path), _cfg())  # type: ignore[arg-type]
    again = await _join(second, project, "anna")

    assert again.room.epoch == epoch
    assert str(again.text).startswith("До перезапуска. ")


async def test__offline_client_edits_merge_after_server_restart_without_duplicates(
    store: FakeStore, tmp_path: Path
) -> None:
    first = CollabManager(store, YStateStore(tmp_path), _cfg())  # type: ignore[arg-type]
    project = uuid4()
    anna = await _join(first, project, "anna")
    await first.shutdown()
    # Пока сервера нет, клиент правит у себя.
    before = anna.doc.get_state()
    anna.text.insert(0, "Оффлайн. ")
    offline = anna.doc.get_update(before)

    second = CollabManager(store, YStateStore(tmp_path), _cfg())  # type: ignore[arg-type]
    room, client = await second.join(project, PATH, FakeConn(), CollabIdentity("anna", "Анна", True))  # type: ignore[arg-type]
    await room.receive(client, create_update_message(offline))
    await room.receive(client, create_sync_message(anna.doc))

    assert str(room.text).count("Первая строка") == 1
    assert str(room.text).startswith("Оффлайн. ")


async def test__awareness__name_is_vouched_by_server_and_removed_on_leave(manager: CollabManager) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    boris = await _join(manager, project, "boris")
    forged = encode_awareness(
        [AwarenessEntry(11, 1, {"user": {"name": "Администратор"}, "cursor": {"a": 1}, "x": "y"})]
    )

    await anna.room.receive(anna.client, bytes([proto.MSG_AWARENESS]) + write_uint(len(forged)) + forged)
    await boris.pump()

    seen = boris.awareness[-1]
    assert seen.state is not None
    color = anna.client.identity.color
    assert seen.state["user"] == {"name": "Anna", "color": color, "colorLight": f"{color}33", "id": "anna"}
    assert seen.state["cursor"] == {"a": 1}
    assert "x" not in seen.state

    manager.leave(anna.room, anna.client)
    await boris.pump()
    assert boris.awareness[-1].state is None


async def test__flush_message__is_acked_with_etag(manager: CollabManager, store: FakeStore) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    await anna.type_at(0, "Х")

    await anna.room.receive(anna.client, bytes([proto.MSG_FLUSH]))

    frame = anna.client.outbox.get_nowait()
    assert frame[0] == proto.MSG_FLUSH_ACK
    assert json.loads(frame[1:]) == {"ok": True, "etag": _etag(store.text or "")}


async def test__idle_room_is_closed_and_saved_after_last_client_leaves(
    manager: CollabManager, store: FakeStore
) -> None:
    project = uuid4()
    anna = await _join(manager, project, "anna")
    await anna.type_at(0, "Конец. ")

    manager.leave(anna.room, anna.client)
    await _settle(0.4)

    assert manager.room_count() == 0
    assert store.text is not None
    assert store.text.startswith("Конец. ")


async def test__oversize_document__is_not_written(tmp_path: Path, store: FakeStore) -> None:
    manager = CollabManager(store, YStateStore(tmp_path), _cfg(max_doc_bytes=1024))  # type: ignore[arg-type]
    anna = await _join(manager, uuid4(), "anna")

    await anna.type_at(0, "я" * 2000)
    await _settle()

    await anna.pump()
    assert store.writes == []
    assert {"type": "error", "code": "too_large"} in anna.events
