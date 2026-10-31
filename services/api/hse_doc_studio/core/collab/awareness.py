"""Кодек обновлений присутствия (протокол awareness из y-protocols) без зависимости от Yjs.

Сервер не верит имени из браузера: он разбирает обновление, подставляет проверенное имя и цвет и
пересобирает его. Формат: varUint(число записей), затем на запись varUint(clientID), varUint(clock),
varString(JSON состояния, `null` значит «ушёл»).
"""

from __future__ import annotations

import json
from dataclasses import dataclass


class AwarenessFormatError(ValueError):
    pass


@dataclass(frozen=True)
class AwarenessEntry:
    client_id: int
    clock: int
    state: dict[str, object] | None


def _read_uint(data: bytes, pos: int) -> tuple[int, int]:
    number = 0
    shift = 0
    while True:
        if pos >= len(data) or shift > 63:
            raise AwarenessFormatError("truncated varuint")
        byte = data[pos]
        pos += 1
        number |= (byte & 0x7F) << shift
        if byte < 0x80:
            return number, pos
        shift += 7


def write_uint(number: int) -> bytes:
    out = bytearray()
    while number > 0x7F:
        out.append(0x80 | (number & 0x7F))
        number >>= 7
    out.append(number)
    return bytes(out)


def decode_awareness(data: bytes, *, max_entries: int = 64, max_state_bytes: int = 4096) -> list[AwarenessEntry]:
    count, pos = _read_uint(data, 0)
    if count > max_entries:
        raise AwarenessFormatError("too many entries")
    entries: list[AwarenessEntry] = []
    for _ in range(count):
        client_id, pos = _read_uint(data, pos)
        clock, pos = _read_uint(data, pos)
        size, pos = _read_uint(data, pos)
        if size > max_state_bytes or pos + size > len(data):
            raise AwarenessFormatError("bad state size")
        try:
            state = json.loads(data[pos : pos + size].decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise AwarenessFormatError("bad state json") from exc
        pos += size
        if state is not None and not isinstance(state, dict):
            raise AwarenessFormatError("state is not an object")
        entries.append(AwarenessEntry(client_id, clock, state))
    return entries


def encode_awareness(entries: list[AwarenessEntry]) -> bytes:
    out = bytearray(write_uint(len(entries)))
    for entry in entries:
        payload = json.dumps(entry.state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        out += write_uint(entry.client_id) + write_uint(entry.clock) + write_uint(len(payload)) + payload
    return bytes(out)
