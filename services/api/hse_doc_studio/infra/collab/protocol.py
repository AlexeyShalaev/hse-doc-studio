"""Сообщения канала совместной правки поверх протокола y-websocket.

Стандартные типы: 0 синхронизация, 1 присутствие. Свои: 9 «сбросить на диск» (ответ 10 с версией файла) и
11 событие сервера (JSON). Все кадры двоичные; первый байт это тип.
"""

from __future__ import annotations

import json
from typing import Any

from pycrdt import read_message

MSG_SYNC = 0
MSG_AWARENESS = 1
MSG_FLUSH = 9
MSG_FLUSH_ACK = 10
MSG_EVENT = 11

SYNC_STEP1 = 0
SYNC_STEP2 = 1
SYNC_UPDATE = 2


def event_frame(payload: dict[str, Any]) -> bytes:
    return bytes([MSG_EVENT]) + json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def flush_ack_frame(ok: bool, etag: str | None) -> bytes:
    return bytes([MSG_FLUSH_ACK]) + json.dumps({"ok": ok, "etag": etag}).encode("utf-8")


def sync_payload(frame: bytes) -> bytes:
    """Тело кадра синхронизации (после типа и подтипа): байты обновления или вектора состояния."""
    return bytes(read_message(frame[2:]))


def message_body(data: bytes) -> bytes:
    """Тело сообщения с префиксом длины (varUint) начиная с `data[0]`."""
    return bytes(read_message(data))
