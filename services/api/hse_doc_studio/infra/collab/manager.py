"""Комнаты совместной правки: Yjs-документ на файл проекта, подключения, запись на диск, слияние с чужими правками.

Источник истины файл проекта. Комната хранит живой текст и отдаёт его на диск через `ITextStore` (блокировка
папки, квота, правочный коммит, как у обычного сохранения). Всё, что меняет файл помимо комнаты (git, агент,
правка в VS Code, другая реплика), подхватывает сверка с диском раз в `poll_interval_s` и перед каждой операцией
над папкой проекта (`flush_folder`): чужая версия сливается трёхсторонне и превращается в операции над общим
текстом, курсоры участников остаются на месте.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import secrets
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from pycrdt import Doc, Text, create_sync_message, create_update_message, handle_sync_message

from hse_doc_studio.api.config.collab import CollabConfig
from hse_doc_studio.core.collab.awareness import (
    AwarenessEntry,
    AwarenessFormatError,
    decode_awareness,
    encode_awareness,
    write_uint,
)
from hse_doc_studio.core.collab.ports import ITextStore
from hse_doc_studio.core.collab.text_diff import diff_edits, merge3
from hse_doc_studio.infra.collab import protocol as proto
from hse_doc_studio.infra.collab.state_store import SavedState, YStateStore

_log = logging.getLogger(__name__)

# Запись комнаты на диск идёт через тот же замок папки, что и остальные операции: чтобы она не сбрасывала
# комнаты заново (а это ждало бы её саму), на время записи ставится этот признак.
IN_COLLAB_PERSIST: contextvars.ContextVar[bool] = contextvars.ContextVar("collab_in_persist", default=False)

# Коды закрытия: 4xxx свои, остальные стандартные.
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_UNSUPPORTED = 4415
CLOSE_BUSY = 4429
CLOSE_TOO_BIG = 1009
CLOSE_OVERLOADED = 1013

_COLOR_COUNT = 8


class CollabRefusedError(Exception):
    """Комната не открывается для этого подключения; `code` это код закрытия сокета."""

    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class CollabConn(Protocol):
    async def send_bytes(self, data: bytes) -> None: ...

    async def close(self, code: int, reason: str) -> None: ...


@dataclass(frozen=True)
class CollabIdentity:
    """Кто подключился: проверенные имя и ключ (id человека или гостевой сессии); цвет считается по ключу."""

    key: str
    name: str
    can_write: bool

    @property
    def color(self) -> str:
        index = sum(self.key.encode("utf-8")) % _COLOR_COUNT
        return f"c{index}"


class _Bucket:
    """Ведро для частоты обновлений курсора: избыток отбрасывается молча."""

    def __init__(self, per_second: int) -> None:
        self._rate = float(per_second)
        self._tokens = float(per_second)
        self._at = time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self._tokens = min(self._rate, self._tokens + (now - self._at) * self._rate)
        self._at = now
        if self._tokens < 1:
            return False
        self._tokens -= 1
        return True


_client_ids = iter(range(1, 1 << 62))


@dataclass
class Client:
    conn: CollabConn
    identity: CollabIdentity
    outbox: asyncio.Queue[bytes | None]
    bucket: _Bucket
    id: int = field(default_factory=lambda: next(_client_ids))
    awareness_ids: set[int] = field(default_factory=set)
    overflowed: bool = False
    notified_read_only: bool = False

    def send(self, frame: bytes) -> None:
        """Ставит кадр в очередь клиента; переполненная очередь значит медленного читателя, его отключают."""
        if self.overflowed:
            return
        try:
            self.outbox.put_nowait(frame)
        except asyncio.QueueFull:
            self.overflowed = True
            # Клиент отстал и пропустил кадры: оставлять его нельзя, при переподключении он синхронизируется заново.
            task = asyncio.ensure_future(self.conn.close(CLOSE_OVERLOADED, "overloaded"))
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


def _utf8_index(text: str, index: int) -> int:
    return len(text[:index].encode("utf-8"))


class Room:
    def __init__(
        self,
        project_id: UUID,
        path: str,
        folder: Path | None,
        store: ITextStore,
        states: YStateStore,
        cfg: CollabConfig,
        on_close: Callable[[Room], None],
    ) -> None:
        self.project_id = project_id
        self.path = path
        self.folder = folder
        self._store = store
        self._states = states
        self._cfg = cfg
        self._on_close = on_close
        self.clients: dict[int, Client] = {}
        self.awareness: dict[int, AwarenessEntry] = {}
        self.doc: Doc[Any] = Doc()
        self.text: Text = self.doc.get("text", type=Text)
        self.epoch = secrets.token_hex(16)
        self.base_text = ""
        self.base_etag: str | None = None
        self.version = 0
        self.saved_version = 0
        self.closed = False
        self.oversize = False
        self._persist_lock = asyncio.Lock()
        self._first_dirty: float | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._idle: asyncio.TimerHandle | None = None
        self._watcher: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    # ── открытие ────────────────────────────────────────────────────────────

    async def open(self) -> None:
        snapshot = await self._store.read(self.project_id, self.path)
        if snapshot is None:
            raise CollabRefusedError(CLOSE_UNSUPPORTED, "not_text")
        if len(snapshot.text.encode("utf-8")) > self._cfg.max_doc_bytes:
            raise CollabRefusedError(CLOSE_TOO_BIG, "too_large")
        if await self._restore_state(len(snapshot.text)):
            if str(self.text) != snapshot.text:
                self._apply_text(snapshot.text, broadcast=False)
        else:
            self.text += snapshot.text
        self.base_text, self.base_etag = snapshot.text, snapshot.etag
        self._watcher = asyncio.create_task(self._watch())

    async def _restore_state(self, text_len: int) -> bool:
        """Поднимает родословную документа из файла состояния; False, если её нет или она непригодна."""
        saved = await asyncio.to_thread(self._states.load, self.project_id, self.path)
        # Состояние, раздутое историей правок больше чем в 20 раз, проще начать заново: комнаты тогда нет.
        if saved is None or len(saved.update) > 20 * text_len + 262_144:
            return False
        try:
            self.doc.apply_update(saved.update)
        except BaseException as exc:
            if isinstance(exc, KeyboardInterrupt | SystemExit):
                raise
            _log.warning("collab state unusable, rebuilding from file", exc_info=True)
            self.doc = Doc()
            self.text = self.doc.get("text", type=Text)
            return False
        self.epoch = saved.epoch
        return True

    # ── изменения документа ─────────────────────────────────────────────────

    def _apply_text(self, new_text: str, *, broadcast: bool = True) -> None:
        """Приводит общий текст к `new_text` минимальными правками и рассылает их всем участникам."""
        old = str(self.text)
        edits = diff_edits(old, new_text)
        if not edits:
            return
        before = self.doc.get_state()
        with self.doc.transaction():
            for edit in reversed(edits):
                start, end = _utf8_index(old, edit.start), _utf8_index(old, edit.end)
                if end > start:
                    del self.text[start:end]
                if edit.insert:
                    self.text.insert(start, edit.insert)
        self.version += 1
        if broadcast:
            self.broadcast(create_update_message(self.doc.get_update(before)))

    def broadcast(self, frame: bytes, *, skip: int | None = None) -> None:
        for client in list(self.clients.values()):
            if client.id != skip:
                client.send(frame)

    def broadcast_event(self, payload: dict[str, object]) -> None:
        self.broadcast(proto.event_frame(payload))

    @property
    def dirty(self) -> bool:
        return self.version != self.saved_version

    def _mark_dirty(self) -> None:
        now = time.monotonic()
        if self._first_dirty is None:
            self._first_dirty = now
        if self._timer is not None:
            self._timer.cancel()
        wait = max(0.0, self._first_dirty + self._cfg.persist_max_wait_s - now)
        self._timer = asyncio.get_running_loop().call_later(
            min(self._cfg.persist_delay_s, wait), lambda: self._spawn(self._persist_quietly())
        )

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ── обмен с клиентом ────────────────────────────────────────────────────

    def attach(self, client: Client) -> None:
        if self._idle is not None:
            self._idle.cancel()
            self._idle = None
        self.clients[client.id] = client
        identity = client.identity
        client.send(
            proto.event_frame(
                {
                    "type": "hello",
                    "epoch": self.epoch,
                    "can_write": identity.can_write,
                    "color": identity.color,
                    "name": identity.name,
                }
            )
        )
        client.send(create_sync_message(self.doc))
        if self.awareness:
            client.send(bytes([proto.MSG_AWARENESS]) + _write_message(encode_awareness(list(self.awareness.values()))))

    def detach(self, client: Client) -> None:
        self.clients.pop(client.id, None)
        gone = [
            AwarenessEntry(cid, self.awareness[cid].clock + 1, None)
            for cid in client.awareness_ids
            if cid in self.awareness
        ]
        for entry in gone:
            self.awareness.pop(entry.client_id, None)
        if gone:
            self.broadcast(bytes([proto.MSG_AWARENESS]) + _write_message(encode_awareness(gone)))
        if not self.clients and not self.closed:
            self._idle = asyncio.get_running_loop().call_later(
                self._cfg.idle_ttl_s, lambda: self._spawn(self.close("idle"))
            )

    async def receive(self, client: Client, data: bytes) -> None:
        if not data:
            return
        kind = data[0]
        if kind == proto.MSG_SYNC and len(data) >= 2:
            await self._on_sync(client, data)
        elif kind == proto.MSG_AWARENESS:
            self._on_awareness(client, data)
        elif kind == proto.MSG_FLUSH:
            ok = await self.persist(force=True)
            client.send(proto.flush_ack_frame(ok, self.base_etag))

    async def _on_sync(self, client: Client, data: bytes) -> None:
        sub = data[1]
        if sub == proto.SYNC_STEP1:
            reply = handle_sync_message(data[1:], self.doc)
            if reply is not None:
                client.send(reply)
        elif sub in (proto.SYNC_STEP2, proto.SYNC_UPDATE):
            if client.identity.can_write:
                await self._apply_client_update(client, data)
            elif not client.notified_read_only:
                # Читатель не пишет: обновление отбрасывается, а клиент один раз узнаёт об этом.
                client.notified_read_only = True
                client.send(proto.event_frame({"type": "read_only"}))

    async def _apply_client_update(self, client: Client, data: bytes) -> None:
        try:
            update = proto.sync_payload(data)
            if update in (b"", b"\x00\x00"):
                return
            self.doc.apply_update(update)
        except BaseException as exc:
            if isinstance(exc, KeyboardInterrupt | SystemExit):
                raise
            _log.warning("collab update rejected", extra={"path": self.path})
            await client.conn.close(1003, "bad_update")
            return
        self.version += 1
        self.broadcast(create_update_message(update), skip=client.id)
        self.oversize = len(self.text) > self._cfg.max_doc_bytes
        if self.oversize:
            self.broadcast_event({"type": "error", "code": "too_large"})
        else:
            self._mark_dirty()

    def _on_awareness(self, client: Client, data: bytes) -> None:
        if not client.bucket.take():
            return
        try:
            body = proto.message_body(data[1:])
            entries = decode_awareness(body)
        except (AwarenessFormatError, ValueError, IndexError):
            return
        accepted: list[AwarenessEntry] = []
        for entry in entries:
            if entry.client_id not in client.awareness_ids and len(client.awareness_ids) >= 2:
                continue
            client.awareness_ids.add(entry.client_id)
            state = _vouched_state(entry.state, client.identity)
            accepted.append(AwarenessEntry(entry.client_id, entry.clock, state))
            if state is None:
                self.awareness.pop(entry.client_id, None)
            else:
                self.awareness[entry.client_id] = accepted[-1]
        if accepted:
            self.broadcast(bytes([proto.MSG_AWARENESS]) + _write_message(encode_awareness(accepted)))

    # ── запись и сверка с диском ────────────────────────────────────────────

    async def _persist_quietly(self) -> None:
        try:
            await self.persist()
        except Exception:
            _log.exception("collab persist failed", extra={"path": self.path})
            self.broadcast_event({"type": "error", "code": "save_failed"})

    @asynccontextmanager
    async def _exclusive(self) -> AsyncIterator[None]:
        """Единственная запись комнаты на диск. Признак на время секции не даёт замку папки сбросить комнату заново."""
        async with self._persist_lock:
            token = IN_COLLAB_PERSIST.set(True)
            try:
                yield
            finally:
                IN_COLLAB_PERSIST.reset(token)

    async def persist(self, *, force: bool = False) -> bool:
        """Записывает текст комнаты на диск. False, если записать не удалось (клиент увидит это в ответе на сброс)."""
        async with self._exclusive():
            if self.closed or (not self.dirty and not force):
                return True
            if self.oversize:
                return False
            self._first_dirty = None
            if not await self._reconcile_locked():
                return True
            return await self._write_locked()

    async def _write_locked(self) -> bool:
        text = str(self.text)
        at_version = self.version
        if text != self.base_text:
            try:
                etag = await self._store.write(self.project_id, self.path, text)
            except Exception:
                _log.exception("collab write failed", extra={"path": self.path})
                self.broadcast_event({"type": "error", "code": "save_failed"})
                return False
            self.base_text, self.base_etag = text, etag
        self.saved_version = at_version
        await self._save_state()
        if self.dirty:
            self._mark_dirty()
        return True

    async def _save_state(self) -> None:
        state = SavedState(self.epoch, bytes(self.doc.get_update()))
        await asyncio.to_thread(self._states.save, self.project_id, self.path, state)

    async def _reconcile_locked(self) -> bool:
        """Подтягивает чужие правки файла в общий текст. False, если файл исчез (комната закрывается)."""
        etag = await self._store.etag(self.project_id, self.path)
        if etag == self.base_etag:
            return True
        snapshot = await self._store.read(self.project_id, self.path)
        if snapshot is None:
            if etag is None:
                await self._file_gone()
                return False
            self.broadcast_event({"type": "error", "code": "not_text"})
            return True
        theirs, ours = snapshot.text, str(self.text)
        conflicts = 0
        if theirs != ours:
            if ours == self.base_text:
                self._apply_text(theirs)
            else:
                merged = merge3(self.base_text, ours, theirs)
                conflicts = merged.conflicts
                if conflicts:
                    await self._store.record_external(self.project_id, self.path)
                self._apply_text(merged.text)
            self.broadcast_event({"type": "external", "conflicts": conflicts})
        self.base_text, self.base_etag = theirs, snapshot.etag
        # Версия после слияния ещё не на диске, если слияние изменило текст относительно файла.
        self.saved_version = self.version if str(self.text) == theirs else self.saved_version
        return True

    async def _file_gone(self) -> None:
        self.broadcast_event({"type": "error", "code": "file_gone"})
        self._spawn(self.close("file_gone", code=CLOSE_NOT_FOUND, drop_state=True))

    async def _watch(self) -> None:
        while not self.closed:
            await asyncio.sleep(self._cfg.poll_interval_s)
            if self._persist_lock.locked() or self.closed:
                continue
            try:
                etag = await self._store.etag(self.project_id, self.path)
                if etag != self.base_etag:
                    async with self._exclusive():
                        if not self.closed:
                            await self._reconcile_locked()
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("collab watch failed", extra={"path": self.path})

    # ── закрытие ────────────────────────────────────────────────────────────

    async def close(self, reason: str, *, code: int = 1001, drop_state: bool = False) -> None:
        if self.closed:
            return
        if not drop_state:
            with suppress(Exception):
                await self.persist(force=self.dirty)
        self.closed = True
        self._on_close(self)
        self._cancel_timers()
        if drop_state:
            await asyncio.to_thread(self._states.drop, self.project_id, self.path)
        else:
            with suppress(Exception):
                await self._save_state()
        for client in list(self.clients.values()):
            client.send(b"")  # сигнал писателю: очередь закрыта
            with suppress(Exception):
                await client.conn.close(code, reason)
        self.clients.clear()

    def _cancel_timers(self) -> None:
        for timer in (self._timer, self._idle):
            if timer is not None:
                timer.cancel()
        if self._watcher is not None and self._watcher is not asyncio.current_task():
            self._watcher.cancel()


def _write_message(data: bytes) -> bytes:
    return write_uint(len(data)) + data


def _vouched_state(state: dict[str, object] | None, identity: CollabIdentity) -> dict[str, object] | None:
    """Присутствие с проверенным именем и цветом; из состояния клиента остаётся только курсор."""
    if state is None:
        return None
    vouched: dict[str, object] = {"user": {"name": identity.name, "color": identity.color, "id": identity.key}}
    cursor = state.get("cursor")
    if isinstance(cursor, dict | type(None)):
        vouched["cursor"] = cursor
    vouched["writable"] = identity.can_write
    return vouched


class CollabManager:
    """Реестр комнат реплики: пределы нагрузки, вход и выход подключений, сброс перед операциями над папкой."""

    def __init__(self, store: ITextStore, states: YStateStore, cfg: CollabConfig) -> None:
        self._store = store
        self._states = states
        self._cfg = cfg
        self._rooms: dict[tuple[UUID, str], Room] = {}
        self._create_lock = asyncio.Lock()
        self._by_user: dict[str, int] = defaultdict(int)

    @property
    def enabled(self) -> bool:
        return self._cfg.enabled

    @property
    def config(self) -> CollabConfig:
        return self._cfg

    def room_count(self) -> int:
        return len(self._rooms)

    def client_count(self) -> int:
        return sum(len(r.clients) for r in self._rooms.values())

    async def join(
        self, project_id: UUID, path: str, conn: CollabConn, identity: CollabIdentity
    ) -> tuple[Room, Client]:
        if not self._cfg.enabled:
            raise CollabRefusedError(CLOSE_UNSUPPORTED, "disabled")
        if self._by_user[identity.key] >= self._cfg.max_connections_per_user:
            raise CollabRefusedError(CLOSE_BUSY, "too_many_connections")
        room = await self._room(project_id, path)
        if len(room.clients) >= self._cfg.max_clients_per_room:
            raise CollabRefusedError(CLOSE_BUSY, "room_full")
        client = Client(
            conn=conn,
            identity=identity,
            outbox=asyncio.Queue(self._cfg.outbox_size),
            bucket=_Bucket(self._cfg.awareness_per_second),
        )
        self._by_user[identity.key] += 1
        room.attach(client)
        return room, client

    async def _room(self, project_id: UUID, path: str) -> Room:
        key = (project_id, path)
        async with self._create_lock:
            room = self._rooms.get(key)
            if room is not None and not room.closed:
                return room
            if len(self._rooms) >= self._cfg.max_rooms_total:
                raise CollabRefusedError(CLOSE_BUSY, "server_busy")
            if sum(1 for k in self._rooms if k[0] == project_id) >= self._cfg.max_rooms_per_project:
                raise CollabRefusedError(CLOSE_BUSY, "project_busy")
            folder = await self._store.folder(project_id)
            if folder is None:
                raise CollabRefusedError(CLOSE_NOT_FOUND, "project_not_found")
            room = Room(project_id, path, folder, self._store, self._states, self._cfg, self._forget)
            await room.open()
            self._rooms[key] = room
            return room

    def _forget(self, room: Room) -> None:
        if self._rooms.get((room.project_id, room.path)) is room:
            del self._rooms[(room.project_id, room.path)]

    def leave(self, room: Room, client: Client) -> None:
        room.detach(client)
        remaining = self._by_user[client.identity.key] - 1
        if remaining > 0:
            self._by_user[client.identity.key] = remaining
        else:
            self._by_user.pop(client.identity.key, None)

    async def flush_folder(self, folder: Path) -> None:
        if IN_COLLAB_PERSIST.get():
            return
        try:
            key = folder.resolve()
        except OSError:
            key = folder
        rooms = [r for r in self._rooms.values() if r.folder is not None and _same(r.folder, key) and r.dirty]
        for room in rooms:
            await room.persist()

    async def review_changed(self, project_id: UUID, path: str) -> None:
        room = self._rooms.get((project_id, path))
        if room is not None:
            room.broadcast_event({"type": "review"})

    async def shutdown(self) -> None:
        for room in list(self._rooms.values()):
            with suppress(Exception):
                await room.close("shutdown")


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b
    except OSError:
        return a == b
