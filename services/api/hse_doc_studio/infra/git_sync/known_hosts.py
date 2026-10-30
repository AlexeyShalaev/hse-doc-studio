"""Собственный known_hosts Студии: `<data_dir>/git/known_hosts` в обычном формате OpenSSH.

Пользовательский ~/.ssh не читается и не меняется. Хеширование имён выключено, чтобы файл можно было
проверить глазами: ключи хостов публичны. Время добавления лежит в комментарии строки
(`hse-added=...`), ssh его игнорирует. Записать в файл можно только ключи, которые подтвердил человек:
эту проверку делает сценарий доверия, здесь она не дублируется.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.core.git_sync.entities import ScannedHostKey
from hse_doc_studio.core.git_sync.host_keys import (
    key_fingerprint,
    known_host_pattern,
    normalize_known_port,
    parse_key_fields,
)
from hse_doc_studio.core.git_sync.protocols import KnownHost
from hse_doc_studio.infra.git_sync.key_store import write_private_file

logger = structlog.get_logger()

_ADDED = "hse-added="
_MAX_BYTES = 2_000_000


class _Entry:
    __slots__ = ("added_at", "key", "pattern", "type")

    def __init__(self, pattern: str, key_type: str, key: str, added_at: datetime) -> None:
        self.pattern = pattern
        self.type = key_type
        self.key = key
        self.added_at = added_at


def _parse_added(comment: str, fallback: datetime) -> datetime:
    for part in comment.split():
        if part.startswith(_ADDED):
            try:
                parsed = datetime.fromisoformat(part.removeprefix(_ADDED))
            except ValueError:
                return fallback
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return fallback


def _split_pattern(pattern: str) -> tuple[str, int | None] | None:
    if pattern.startswith("["):
        host, sep, port = pattern[1:].partition("]:")
        if sep and port.isdigit():
            return host, int(port)
        return None
    return pattern, None


# Псевдонимы: внутри класса имя `list` занято методом и в аннотациях означало бы его.
_Entries = list[_Entry]
_Hosts = list[KnownHost]


class FileKnownHostsStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "git" / "known_hosts"
        self._lock = threading.Lock()

    def file_path(self) -> Path:
        return self._path

    async def materialize(self) -> None:
        """Источник правды здесь сам файл known_hosts."""

    async def list(self) -> _Hosts:
        return self._group(self._read())

    async def find(self, host: str, port: int | None) -> KnownHost | None:
        pattern = known_host_pattern(host, port)
        found = self._group([entry for entry in self._read() if entry.pattern == pattern])
        return found[0] if found else None

    async def trust(
        self, host: str, port: int | None, keys: Sequence[ScannedHostKey], *, replace: bool = False
    ) -> None:
        pattern = known_host_pattern(host, port)
        now = datetime.now(timezone.utc)
        with self._lock:
            entries = self._read()
            if replace:
                entries = [entry for entry in entries if entry.pattern != pattern]
            known = {(entry.pattern, entry.type, entry.key) for entry in entries}
            for key in keys:
                if parse_key_fields(key.type, key.key) is None:
                    continue
                if (pattern, key.type, key.key) not in known:
                    entries.append(_Entry(pattern, key.type, key.key, now))
            self._write(entries)

    async def forget(self, host: str, port: int | None) -> None:
        pattern = known_host_pattern(host, port)
        with self._lock:
            entries = self._read()
            kept = [entry for entry in entries if entry.pattern != pattern]
            if len(kept) != len(entries):
                self._write(kept)

    def _read(self) -> _Entries:
        try:
            if self._path.stat().st_size > _MAX_BYTES:
                logger.warning("known_hosts is too large to read", size_limit=_MAX_BYTES)
                return []
            text = self._path.read_text(encoding="utf-8", errors="replace")
            fallback = datetime.fromtimestamp(self._path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return []
        entries: _Entries = []
        for line in text.splitlines():
            fields = line.split(None, 3)
            if len(fields) < 3 or fields[0].startswith(("#", "|", "@")):
                continue
            parsed = parse_key_fields(fields[1], fields[2])
            if parsed is None or "," in fields[0] or _split_pattern(fields[0]) is None:
                continue
            added = _parse_added(fields[3], fallback) if len(fields) > 3 else fallback
            entries.append(_Entry(fields[0], parsed[0], parsed[1], added))
        return entries

    def _write(self, entries: _Entries) -> None:
        lines = [
            f"{entry.pattern} {entry.type} {entry.key} {_ADDED}{entry.added_at.isoformat(timespec='seconds')}"
            for entry in entries
        ]
        write_private_file(self._path, ("\n".join(lines) + "\n" if lines else "").encode("utf-8"))

    @staticmethod
    def _group(entries: _Entries) -> _Hosts:
        grouped: dict[str, list[_Entry]] = {}
        for entry in entries:
            grouped.setdefault(entry.pattern, []).append(entry)
        hosts: _Hosts = []
        for pattern, items in grouped.items():
            split = _split_pattern(pattern)
            if split is None:
                continue
            host, port = split
            hosts.append(
                KnownHost(
                    host=host,
                    port=normalize_known_port(port),
                    key_types=tuple(dict.fromkeys(item.type for item in items)),
                    fingerprints_sha256=tuple(dict.fromkeys(key_fingerprint(item.key) for item in items)),
                    added_at=min(item.added_at for item in items),
                )
            )
        return sorted(hosts, key=lambda h: (h.host, h.port or 0))
