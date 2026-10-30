"""Каналы ретрансляции ИИ в памяти api: порции событий раннера превращаются в поток тела ответа модели.

Канал живёт в той реплике api, которая поставила задачу (как `JobWakeup`); после рестарта api раннер получает
`cancel` и 404 на тело. Буфер ограничен: пока потребитель не прочитал, ручка раннера не отвечает подтверждением,
и раннер ждёт (обратное давление), поэтому быстрый раннер не раздувает память api.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.queue import QueuedJob
from hse_doc_studio.core.jobs.relay import (
    MAX_RELAY_BATCH_BYTES,
    MAX_RELAY_EVENT_BYTES,
    RelayErrorCode,
    RelayEventKind,
    RelayOutOfOrderError,
    RelayStreamError,
    RelayTooLargeError,
)
from hse_doc_studio.core.jobs.wire import RelayEvent

logger = structlog.get_logger(__name__)

# Сколько порций данных канал держит, пока потребитель не прочитал (до 64 KiB каждая).
DEFAULT_BUFFER_CHUNKS = 64


@dataclass(frozen=True)
class _End:
    pass


@dataclass(frozen=True)
class _Fail:
    code: str


type _Item = bytes | _End | _Fail


class RelayChannel:
    """Состояние одной ретрансляции; методы потребителя и раннера зовутся из одного цикла событий."""

    def __init__(self, job_id: UUID, *, buffer_chunks: int = DEFAULT_BUFFER_CHUNKS) -> None:
        self.job_id = job_id
        self._picked = asyncio.Event()
        self._head: asyncio.Future[tuple[int, str | None]] = asyncio.get_running_loop().create_future()
        self._items: asyncio.Queue[_Item] = asyncio.Queue(maxsize=buffer_chunks)
        self._last_seq = -1
        self._finished = False
        self._consumer_closed = False
        self._lock = asyncio.Lock()

    # Сторона потребителя.

    async def wait_picked(self, timeout_s: float) -> bool:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._picked.wait(), timeout_s)
        return self._picked.is_set()

    async def wait_head(self, timeout_s: float) -> tuple[int, str | None]:
        return await asyncio.wait_for(asyncio.shield(self._head), timeout_s)

    async def read(self, timeout_s: float) -> bytes | None:
        item = await asyncio.wait_for(self._items.get(), timeout_s)
        if isinstance(item, _End):
            return None
        if isinstance(item, _Fail):
            raise RelayStreamError(item.code)
        return item

    def close(self) -> None:
        self._consumer_closed = True
        self._drain()

    @property
    def consumer_closed(self) -> bool:
        return self._consumer_closed

    # Сторона раннера.

    def mark_picked(self) -> None:
        self._picked.set()

    async def push(self, seq: int, events: tuple[RelayEvent, ...]) -> bool:
        """Принимает порцию строго по порядку; повтор принятой порции безвреден. Возвращает `cancel`."""
        async with self._lock:
            if seq <= self._last_seq:
                return self._consumer_closed
            if seq != self._last_seq + 1:
                raise RelayOutOfOrderError(f"expected batch {self._last_seq + 1}, got {seq}")
            decoded = self._validate(events)
            self._last_seq = seq
            for event, data in zip(events, decoded, strict=True):
                await self._apply(event, data)
            return self._consumer_closed

    def fail(self, code: str) -> None:
        """Обрыв без `end`: потребитель получает `RelayStreamError`; после `end` ничего не меняет."""
        if self._finished:
            return
        self._finished = True
        self._picked.set()
        if not self._head.done():
            self._head.set_exception(RelayStreamError(code))
            # Исключение будущего потребитель может и не забрать (уже ушёл): не шумим в журнал.
            self._head.exception()
        self._put_nowait_dropping(_Fail(code))

    def _validate(self, events: tuple[RelayEvent, ...]) -> list[bytes | None]:
        """Порядок head, data, end или error и пределы проверяются до того, как канал что-то примет."""
        head_seen = self._head.done()
        finished = self._finished
        for event in events:
            head_seen, finished = _next_order(event.kind, head_seen=head_seen, finished=finished)
        decoded = [_decode(event) if event.kind is RelayEventKind.data else None for event in events]
        sizes = [len(data) for data in decoded if data is not None]
        if any(size > MAX_RELAY_EVENT_BYTES for size in sizes):
            raise RelayTooLargeError("relay event is larger than 64 KiB")
        if sum(sizes) > MAX_RELAY_BATCH_BYTES:
            raise RelayTooLargeError("relay batch is larger than 256 KiB")
        return decoded

    async def _apply(self, event: RelayEvent, data: bytes | None) -> None:
        if event.kind is RelayEventKind.head:
            assert event.status is not None  # noqa: S101 — проверено в RelayEvent
            self._head.set_result((event.status, event.content_type))
        elif event.kind is RelayEventKind.data and data is not None:
            await self._put(data)
        elif event.kind is RelayEventKind.end:
            self._finished = True
            await self._put(_End())
        elif event.kind is RelayEventKind.error:
            self.fail(event.code or RelayErrorCode.relay_unavailable.value)

    async def _put(self, item: _Item) -> None:
        if self._consumer_closed:
            return
        # Ждём место в буфере; закрытие потребителем опустошает буфер, и ожидание кончается.
        await self._items.put(item)
        if self.consumer_closed:
            self._drain()

    def _put_nowait_dropping(self, item: _Item) -> None:
        if self._consumer_closed:
            return
        while True:
            try:
                self._items.put_nowait(item)
            except asyncio.QueueFull:
                # Обрыв важнее непрочитанных данных: потребитель всё равно получит ошибку.
                self._items.get_nowait()
            else:
                return

    def _drain(self) -> None:
        while not self._items.empty():
            self._items.get_nowait()


def _next_order(kind: RelayEventKind, *, head_seen: bool, finished: bool) -> tuple[bool, bool]:
    """Ровно один head раньше любых data и end; после end или error событий нет."""
    if finished:
        raise RelayOutOfOrderError("events after end or error")
    if kind is RelayEventKind.head:
        if head_seen:
            raise RelayOutOfOrderError("second head")
        return True, False
    if kind in (RelayEventKind.data, RelayEventKind.end) and not head_seen:
        raise RelayOutOfOrderError(f"{kind.value} before head")
    return head_seen, kind in (RelayEventKind.end, RelayEventKind.error)


def _decode(event: RelayEvent) -> bytes:
    try:
        return base64.b64decode(event.data or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RelayOutOfOrderError("data is not base64") from exc


class RelayHub:
    """`IRelayHub` и слушатель терминального состояния: задача кончилась без `end`, поток рвётся с её кодом."""

    def __init__(self, *, buffer_chunks: int = DEFAULT_BUFFER_CHUNKS) -> None:
        self._channels: dict[UUID, RelayChannel] = {}
        self._buffer_chunks = buffer_chunks

    def open(self, job_id: UUID) -> RelayChannel:
        channel = RelayChannel(job_id, buffer_chunks=self._buffer_chunks)
        self._channels[job_id] = channel
        return channel

    def discard(self, job_id: UUID) -> None:
        self._channels.pop(job_id, None)

    def get(self, job_id: UUID) -> RelayChannel | None:
        return self._channels.get(job_id)

    def mark_picked(self, job_id: UUID) -> bool:
        channel = self._channels.get(job_id)
        if channel is None:
            return False
        channel.mark_picked()
        return True

    async def push(self, job_id: UUID, seq: int, events: tuple[RelayEvent, ...]) -> bool:
        channel = self._channels.get(job_id)
        if channel is None:
            return True
        return await channel.push(seq, events)

    def fail(self, job_id: UUID, code: str) -> None:
        channel = self._channels.get(job_id)
        if channel is not None:
            channel.fail(code)

    @property
    def open_channels(self) -> int:
        return len(self._channels)

    async def on_terminal(self, job: QueuedJob) -> None:
        channel = self._channels.get(job.id)
        if channel is None:
            return
        logger.info("relay_job_terminal", job_id=str(job.id), state=job.state.value, error_code=job.error_code)
        channel.fail(_terminal_code(job))


def _terminal_code(job: QueuedJob) -> str:
    """Код обрыва по записи очереди: потеря раннера и отмена в очереди для человека значат «раннер не ответил»."""
    if job.state is JobState.succeeded:
        return RelayErrorCode.relay_unavailable.value
    code = job.error_code
    if code is None or code in ("runner_lost", "superseded", "relay_unavailable"):
        return RelayErrorCode.relay_unavailable.value
    return code
