"""Доверие к git-серверам в Postgres: настройки хостов и ключи ssh на уровне установки.

Читает любой пользователь (результат проверки нужен каждому), менять доверие может только админ установки.
Единственное исключение: кэш определения провайдера (`detected`) обновляет сам сервис при проверке адреса от имени
любого пользователя или фоновой задачи, доверия он не меняет.

git читает не базу, а файлы: `materialize` приводит каталог выполнения в соответствие с таблицами перед каждой
командой. Файл заменяется атомарно и только при расхождении хеша, лишние файлы удаляются, так что удалённая запись
не доживает до следующего запуска git.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import delete, select

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.git_sync.entities import ScannedHostKey
from hse_doc_studio.core.git_sync.host_keys import (
    key_fingerprint,
    known_host_pattern,
    normalize_known_port,
    parse_key_fields,
)
from hse_doc_studio.core.git_sync.host_settings import GitHostSettings, host_settings_key
from hse_doc_studio.core.git_sync.protocols import KnownHost
from hse_doc_studio.core.git_sync.providers import ApiDetection, GitProvider
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode, message_for
from hse_doc_studio.infra.db.orm.git_trust import GitHostSettingsRow, GitKnownHostRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.secrets.key_store import write_private_file

logger = structlog.get_logger()

_ADDED = "hse-added="


def _require_admin() -> str | None:
    actor = current_actor()
    if actor is None or not actor.is_instance_admin:
        raise IdentityError(IdentityErrorCode.forbidden, message_for(IdentityErrorCode.forbidden))
    return actor.id


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _same_file(path: Path, data: bytes) -> bool:
    try:
        return _sha(path.read_bytes()) == _sha(data)
    except OSError:
        return False


# Псевдонимы: внутри классов имя `list` занято методом и в аннотациях означало бы его.
_Items = list[GitHostSettings]
_Rows = list[GitKnownHostRow]
_Hosts = list[KnownHost]


def _prune(directory: Path, keep: set[str], *, suffix: str) -> None:
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name.endswith(suffix) and entry.name not in keep:
            entry.unlink(missing_ok=True)


def _to_entity(row: GitHostSettingsRow) -> GitHostSettings:
    detected = row.detected
    return GitHostSettings(
        host=row.host,
        port=row.port,
        provider_override=None if row.provider_override is None else GitProvider(row.provider_override),
        ca_pem=row.ca_pem,
        pinned_fingerprint=row.pinned_fingerprint,
        pinned_pem=row.pinned_pem,
        detected=None
        if detected is None
        else ApiDetection(GitProvider(detected["provider"]), detected.get("version"), detected.get("api_base")),  # type: ignore[arg-type]
    )


def _trust_part(settings: GitHostSettings | None) -> tuple[object, ...]:
    """Всё, что решает, кому верит Студия: изменение этих полей требует админа."""
    if settings is None:
        return (None, None, None, None)
    return (settings.provider_override, settings.ca_pem, settings.pinned_fingerprint, settings.pinned_pem)


class PostgresGitHostSettingsRepository:
    """IGitHostSettingsRepository сервера; PEM для git лежат в `<runtime_dir>/trust/`."""

    def __init__(self, sessions: SessionProvider, runtime_dir: Path) -> None:
        self._sessions = sessions
        self._dir = runtime_dir / "trust"
        self._lock = asyncio.Lock()
        self._paths: dict[str, Path] = {}

    async def get(self, host: str, port: int | None) -> GitHostSettings | None:
        async with self._sessions.use() as session:
            row = await session.get(GitHostSettingsRow, host_settings_key(host, port))
        return None if row is None else _to_entity(row)

    async def list(self) -> _Items:
        async with self._sessions.use() as session:
            rows = (await session.execute(select(GitHostSettingsRow).order_by(GitHostSettingsRow.key))).scalars()
            return [_to_entity(row) for row in rows]

    async def save(self, settings: GitHostSettings) -> None:
        async with self._sessions.use() as session:
            row = await session.get(GitHostSettingsRow, settings.key)
            before = None if row is None else _to_entity(row)
            admin_id: str | None = None
            if _trust_part(before) != _trust_part(settings):
                admin_id = _require_admin()
            if settings.is_empty:
                if row is not None:
                    await session.delete(row)
                return
            actor = current_actor()
            values = _record(settings)
            if row is None:
                session.add(
                    GitHostSettingsRow(
                        **values,
                        updated_by=admin_id or (actor.id if actor and actor.is_instance_admin else None),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                return
            for name, value in values.items():
                setattr(row, name, value)
            if admin_id is not None:
                row.updated_by = admin_id
            row.updated_at = datetime.now(timezone.utc)
        logger.info("git host settings saved", host=settings.host, port=settings.port, empty=settings.is_empty)

    async def materialize(self) -> None:
        async with self._lock:
            items = [item for item in await self.list() if item.has_trust]
            desired: dict[str, bytes] = {}
            paths: dict[str, Path] = {}
            for item in items:
                bundle = "".join(pem.rstrip("\n") + "\n" for pem in (item.ca_pem, item.pinned_pem) if pem)
                name = f"{hashlib.sha256(item.key.encode()).hexdigest()[:24]}.pem"
                desired[name] = bundle.encode("ascii")
                paths[item.key] = self._dir / name
            for name, data in desired.items():
                if not _same_file(self._dir / name, data):
                    write_private_file(self._dir / name, data)
            _prune(self._dir, set(desired), suffix=".pem")
            self._paths = paths

    def trust_file(self, host: str, port: int | None) -> Path | None:
        return self._paths.get(host_settings_key(host, port))


def _record(settings: GitHostSettings) -> dict[str, object]:
    detected = settings.detected
    return {
        "key": settings.key,
        "host": settings.host,
        "port": settings.port,
        "provider_override": None if settings.provider_override is None else settings.provider_override.value,
        "ca_pem": settings.ca_pem,
        "pinned_fingerprint": settings.pinned_fingerprint,
        "pinned_pem": settings.pinned_pem,
        "detected": None
        if detected is None
        else {"provider": detected.provider.value, "version": detected.version, "api_base": detected.api_base},
    }


class PostgresKnownHostsStore:
    """IKnownHostsStore сервера; known_hosts для ssh лежит в `<runtime_dir>/known_hosts`."""

    def __init__(self, sessions: SessionProvider, runtime_dir: Path) -> None:
        self._sessions = sessions
        self._path = runtime_dir / "known_hosts"
        self._lock = asyncio.Lock()

    def file_path(self) -> Path:
        return self._path

    async def list(self) -> _Hosts:
        return self._group(await self._rows())

    async def find(self, host: str, port: int | None) -> KnownHost | None:
        pattern = known_host_pattern(host, port)
        found = self._group([row for row in await self._rows() if row.pattern == pattern])
        return found[0] if found else None

    async def trust(
        self, host: str, port: int | None, keys: Sequence[ScannedHostKey], *, replace: bool = False
    ) -> None:
        trusted_by = _require_admin()
        pattern = known_host_pattern(host, port)
        now = datetime.now(timezone.utc)
        async with self._sessions.use() as session:
            if replace:
                await session.execute(delete(GitKnownHostRow).where(GitKnownHostRow.pattern == pattern))
            known = {
                (row.key_type, row.fingerprint)
                for row in (
                    await session.execute(select(GitKnownHostRow).where(GitKnownHostRow.pattern == pattern))
                ).scalars()
            }
            for key in keys:
                if parse_key_fields(key.type, key.key) is None:
                    continue
                fingerprint = key_fingerprint(key.key)
                if (key.type, fingerprint) in known:
                    continue
                known.add((key.type, fingerprint))
                session.add(
                    GitKnownHostRow(
                        pattern=pattern,
                        key_type=key.type,
                        fingerprint=fingerprint,
                        host=host,
                        port=normalize_known_port(port),
                        key=key.key,
                        trusted_by=trusted_by,
                        added_at=now,
                    )
                )

    async def forget(self, host: str, port: int | None) -> None:
        _require_admin()
        async with self._sessions.use() as session:
            await session.execute(
                delete(GitKnownHostRow).where(GitKnownHostRow.pattern == known_host_pattern(host, port))
            )

    async def materialize(self) -> None:
        async with self._lock:
            rows = await self._rows()
            lines = [
                f"{row.pattern} {row.key_type} {row.key} {_ADDED}{row.added_at.isoformat(timespec='seconds')}"
                for row in rows
            ]
            data = ("\n".join(lines) + "\n" if lines else "").encode("utf-8")
            if not _same_file(self._path, data):
                write_private_file(self._path, data)

    async def _rows(self) -> _Rows:
        stmt = select(GitKnownHostRow).order_by(
            GitKnownHostRow.pattern, GitKnownHostRow.key_type, GitKnownHostRow.fingerprint
        )
        async with self._sessions.use() as session:
            rows = list((await session.execute(stmt)).scalars())
            session.expunge_all()
        return rows

    @staticmethod
    def _group(rows: _Rows) -> _Hosts:
        grouped: dict[str, list[GitKnownHostRow]] = {}
        for row in rows:
            grouped.setdefault(row.pattern, []).append(row)
        hosts = [
            KnownHost(
                host=items[0].host,
                port=normalize_known_port(items[0].port),
                key_types=tuple(dict.fromkeys(item.key_type for item in items)),
                fingerprints_sha256=tuple(dict.fromkeys(item.fingerprint for item in items)),
                added_at=min(item.added_at for item in items),
            )
            for items in grouped.values()
        ]
        return sorted(hosts, key=lambda h: (h.host, h.port or 0))
