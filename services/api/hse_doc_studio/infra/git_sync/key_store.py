"""Ключи шифрования секретов: файл в data_dir или ключ из окружения.

Файл `secrets/master.keys.json` создаётся лениво, при первом сохранении секрета, и никогда
не перезаписывается (при одновременном создании двумя процессами остаётся ключ первого): повреждённый
файл откладывается рядом под другим именем, а ключи, записанные в старом файле, остаются на диске. Файл, который не удалось прочитать (сбой чтения, а не негодное
содержимое), не трогается вовсе: ключ не создаётся, пока файл не прочитается. Формат допускает
несколько ключей (первый в `primary` пишет, остальные читают), поэтому смену ключа можно добавить,
не меняя файлов.

Ключ из окружения (`HSE_STUDIO__SECRETS__KEY` или `HSE_STUDIO__SECRETS__KEY_FILE`) выключает
запись файла целиком: так ключ можно держать вне тома с данными (docker secrets).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from cryptography.fernet import Fernet

from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import CipherStatus, KeySource
from hse_doc_studio.core.i18n import localized_error

logger = structlog.get_logger()

ENV_KEY_ID = "env"
_FILE_VERSION = 1
_KEY_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_GROUP_OTHER_BITS = 0o077


@dataclass(frozen=True)
class KeyRing:
    """Ключи Fernet по идентификаторам и тот, которым шифруются новые секреты."""

    primary_id: str
    keys: dict[str, bytes]


def _unavailable() -> GitSyncError:
    return GitSyncError(
        GitErrorCode.secrets_unavailable,
        localized_error(
            "Ключ шифрования недоступен: сохранённые токены прочитать нельзя. Введите их заново.",
            "The encryption key is unavailable: saved tokens cannot be read. Enter them again.",
        ),
    )


def store_unavailable_error() -> GitSyncError:
    """Файл хранилища не прочитался (сбой, а не негодное содержимое): запись остановлена, файл не тронут."""
    return GitSyncError(
        GitErrorCode.secrets_unavailable,
        localized_error(
            "Хранилище доступов сейчас недоступно, ничего не изменено. Повторите попытку.",
            "The credentials storage is unavailable right now; nothing was changed. Try again.",
        ),
    )


def _fernet_key(raw: str) -> bytes | None:
    key = raw.strip().encode()
    try:
        Fernet(key)
    except (ValueError, TypeError):
        return None
    return key


class KeyFileStore:
    def __init__(self, path: Path, *, env_key: str | None = None, env_key_file: Path | None = None) -> None:
        self._path = path
        self._env_key = env_key or None
        self._env_key_file = env_key_file
        self._lock = threading.Lock()

    @property
    def source(self) -> KeySource:
        return KeySource.env if self._env_key or self._env_key_file else KeySource.file

    def load(self) -> KeyRing | None:
        """Прочитать ключи; None, если их нет или файл негоден. Ничего не пишет."""
        if self.source is KeySource.env:
            return self._load_env()
        return self._read_file()[0]

    def ensure_primary(self) -> KeyRing:
        """Ключи для записи нового секрета: при необходимости создаёт файл, повреждённый откладывает в сторону."""
        if self.source is KeySource.env:
            ring = self._load_env()
            if ring is None:
                raise _unavailable()
            return ring
        with self._lock:
            ring, state = self._read_file()
            if ring is not None:
                return ring
            if state == "unreadable":
                # Сбой чтения не доказывает, что ключа нет: новый ключ сделал бы все токены нечитаемыми.
                raise _unavailable()
            if state == "corrupt":
                self._set_aside()
            return self._create()

    def status(self) -> CipherStatus:
        if self.source is KeySource.env:
            return CipherStatus(KeySource.env, available=self._load_env() is not None, permissions_enforced=True)
        _ring, state = self._read_file()
        return CipherStatus(
            KeySource.file,
            available=state not in {"corrupt", "unreadable"},
            permissions_enforced=self._permissions_ok(),
        )

    def _load_env(self) -> KeyRing | None:
        raw = self._env_key
        if raw is None and self._env_key_file is not None:
            try:
                raw = self._env_key_file.read_text(encoding="utf-8")
            except OSError:
                logger.warning("secrets key file is not readable")
                return None
        key = _fernet_key(raw or "")
        if key is None:
            logger.warning("secrets key from the environment is not a valid Fernet key")
            return None
        return KeyRing(ENV_KEY_ID, {ENV_KEY_ID: key})

    def _read_file(self) -> tuple[KeyRing | None, str]:
        """Ключи и состояние файла: missing, ok, corrupt (прочитан, но негоден) или unreadable (чтение не удалось)."""
        try:
            if not self._path.exists():
                return None, "missing"
            content = self._path.read_bytes()
        except OSError:
            # Блокировка клиентом синхронизации, нехватка дескрипторов, EIO: файл мог остаться целым.
            logger.warning("secrets key file is not readable", path=str(self._path))
            return None, "unreadable"
        try:
            ring = self._parse(json.loads(content))
        except ValueError:
            ring = None
        if ring is None:
            logger.warning("secrets key file is damaged", path=str(self._path))
            return None, "corrupt"
        return ring, "ok"

    @staticmethod
    def _parse(data: Any) -> KeyRing | None:
        if not isinstance(data, dict) or data.get("version") != _FILE_VERSION:
            return None
        entries = data.get("keys")
        primary = data.get("primary")
        if not isinstance(entries, list) or not entries or not isinstance(primary, str):
            return None
        keys: dict[str, bytes] = {}
        for entry in entries:
            key_id = entry.get("id") if isinstance(entry, dict) else None
            raw = entry.get("fernet_key") if isinstance(entry, dict) else None
            if not isinstance(key_id, str) or not _KEY_ID.match(key_id) or not isinstance(raw, str):
                return None
            key = _fernet_key(raw)
            if key is None:
                return None
            keys[key_id] = key
        return KeyRing(primary, keys) if primary in keys else None

    def _set_aside(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        target = self._path.with_name(f"{self._path.name}.corrupt-{stamp}")
        try:
            os.replace(self._path, target)
        except OSError as exc:
            logger.exception("could not set the damaged key file aside")
            raise _unavailable() from exc
        logger.warning("damaged secrets key file set aside", aside=target.name)

    def _create(self) -> KeyRing:
        key = Fernet.generate_key()
        # Идентификатор случайный: после потери файла новый ключ не должен выглядеть как старый.
        key_id = f"k{secrets.token_hex(4)}"
        ring = KeyRing(key_id, {key_id: key})
        payload = {
            "version": _FILE_VERSION,
            "primary": ring.primary_id,
            "keys": [
                {
                    "id": ring.primary_id,
                    "fernet_key": key.decode(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
        try:
            created = write_private_file(self._path, json.dumps(payload, indent=2).encode(), exclusive=True)
        except OSError as exc:
            logger.exception("could not write the secrets key file")
            raise _unavailable() from exc
        if not created:
            # Другой процесс успел раньше: его ключ уже мог зашифровать токены, поэтому берём именно его.
            ring, _state = self._read_file()
            if ring is None:
                raise _unavailable()
            logger.info("secrets key file was created by another process", path=str(self._path))
            return ring
        logger.info("secrets key file created", path=str(self._path))
        return ring

    def _permissions_ok(self) -> bool:
        if os.name != "posix":
            return False
        try:
            return not (self._path.stat().st_mode & _GROUP_OTHER_BITS)
        except OSError:
            return True


def write_private_file(path: Path, data: bytes, *, exclusive: bool = False) -> bool:
    """Атомарная запись файла с правами 0600 в каталоге 0700: чужим пользователям машины он не виден.

    `exclusive` не заменяет существующий файл: временный файл привязывается к имени через `os.link`, и если имя
    занято, возвращается False (файл уже создал кто-то другой, в том числе другой процесс). Без `exclusive`
    файл заменяется, результат всегда True.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        logger.debug("could not restrict the secrets directory", path=str(path.parent))
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            return _link_exclusive(tmp, path)
        os.replace(tmp, path)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def _link_exclusive(tmp: Path, path: Path) -> bool:
    try:
        os.link(tmp, path)
    except FileExistsError:
        return False
    except OSError:
        # Файловая система без жёстких ссылок: O_EXCL всё равно не даёт затереть чужой файл.
        return _create_exclusive(tmp, path)
    return True


def _create_exclusive(tmp: Path, path: Path) -> bool:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as handle:
        handle.write(tmp.read_bytes())
        handle.flush()
        os.fsync(handle.fileno())
    return True
