"""Настройки серверов: `<data_dir>/git/host_settings.json` и собранные из них файлы PEM для git.

Файл и каталог закрыты так же, как у доступов (0600 и 0700). Файл PEM собирается заново, когда его нет или он
отличается от записи: git читает путь, а источником правды остаётся JSON. Повреждённый файл откладывается рядом,
в лог попадают только имена серверов.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.git_sync.host_settings import GitHostSettings, host_settings_key
from hse_doc_studio.core.git_sync.providers import ApiDetection, GitProvider
from hse_doc_studio.infra.git_sync.key_store import store_unavailable_error, write_private_file

logger = structlog.get_logger()

_FILE_VERSION = 1

# Псевдоним: внутри класса имя `list` занято методом и в аннотациях означало бы его.
_Items = list[GitHostSettings]


def _to_record(settings: GitHostSettings) -> dict[str, Any]:
    detected = settings.detected
    return {
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


def _from_record(raw: dict[str, Any]) -> GitHostSettings:
    override = raw.get("provider_override")
    detected = raw.get("detected")
    return GitHostSettings(
        host=str(raw["host"]),
        port=raw.get("port"),
        provider_override=None if override is None else GitProvider(override),
        ca_pem=raw.get("ca_pem"),
        pinned_fingerprint=raw.get("pinned_fingerprint"),
        pinned_pem=raw.get("pinned_pem"),
        detected=None
        if detected is None
        else ApiDetection(GitProvider(detected["provider"]), detected.get("version"), detected.get("api_base")),
    )


class JsonGitHostSettingsRepository:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "git" / "host_settings.json"
        self._trust_dir = data_dir / "git" / "trust"
        self._lock = threading.RLock()

    def get(self, host: str, port: int | None) -> GitHostSettings | None:
        wanted = host_settings_key(host, port)
        return next((item for item in self.list() if item.key == wanted), None)

    def list(self) -> _Items:
        with self._lock:
            return self._read(for_write=False)

    def save(self, settings: GitHostSettings) -> None:
        with self._lock:
            kept = [item for item in self._read(for_write=True) if item.key != settings.key]
            if not settings.is_empty:
                kept.append(settings)
            self._write(kept)
        logger.info("git host settings saved", host=settings.host, port=settings.port, empty=settings.is_empty)

    def trust_file(self, host: str, port: int | None) -> Path | None:
        settings = self.get(host, port)
        if settings is None or not settings.has_trust:
            return None
        bundle = "".join(pem.rstrip("\n") + "\n" for pem in (settings.ca_pem, settings.pinned_pem) if pem)
        digest = hashlib.sha256(settings.key.encode()).hexdigest()[:24]
        path = self._trust_dir / f"{digest}.pem"
        with self._lock:
            try:
                current = path.read_text(encoding="ascii") if path.exists() else None
            except (OSError, ValueError):
                current = None
            if current != bundle:
                write_private_file(path, bundle.encode("ascii"))
        return path

    def _content(self, *, for_write: bool) -> bytes | None:
        """Байты файла; None, если файла нет или он не прочитался и пишущему это не мешает.

        Сбой чтения не считается порчей: читающему пусто, пишущий получает ошибку и файл остаётся на месте.
        """
        try:
            return self._path.read_bytes() if self._path.exists() else None
        except OSError as exc:
            logger.warning("git host settings file is not readable", path=str(self._path))
            if for_write:
                raise store_unavailable_error() from exc
            return None

    def _read(self, *, for_write: bool) -> _Items:
        content = self._content(for_write=for_write)
        if content is None:
            return []
        try:
            data = json.loads(content)
            records = data["hosts"] if data.get("version") == _FILE_VERSION else None
        except (ValueError, KeyError, AttributeError):
            records = None
        if not isinstance(records, list):
            logger.warning("git host settings file is damaged", path=str(self._path))
            if for_write:
                self._set_aside()
            return []
        result: _Items = []
        for raw in records:
            try:
                result.append(_from_record(raw))
            except (KeyError, ValueError, TypeError, AttributeError):
                logger.warning("git host settings file: skipped a malformed record")
        return result

    def _set_aside(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self._path.replace(self._path.with_name(f"{self._path.name}.corrupt-{stamp}"))

    def _write(self, items: _Items) -> None:
        payload = {"version": _FILE_VERSION, "hosts": [_to_record(item) for item in items]}
        write_private_file(self._path, json.dumps(payload, ensure_ascii=False, indent=2).encode())
