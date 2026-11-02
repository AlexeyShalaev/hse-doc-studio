"""Манифест бэкапа: сериализация и строгий разбор."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from hse_doc_studio.core.backup.entities import (
    MANIFEST_FORMAT,
    EncryptionMode,
    Manifest,
    ManifestPart,
)
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode

_BACKUP_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{6}")
_SHA = re.compile(r"[0-9a-f]{64}")


def is_backup_id(value: str) -> bool:
    return _BACKUP_ID.fullmatch(value) is not None


def dump_manifest(manifest: Manifest) -> bytes:
    body = {
        "format": manifest.format,
        "backup_id": manifest.backup_id,
        "created_at": manifest.created_at.isoformat(),
        "app_version": manifest.app_version,
        "schema_revision": manifest.schema_revision,
        "installation_id": manifest.installation_id,
        "encryption": {
            "mode": manifest.encryption_mode.value,
            "salt": manifest.salt_hex,
            "key_check": manifest.key_check,
            "key_fingerprint": manifest.key_fingerprint,
        },
        "parts": [
            {
                "name": part.name,
                "size": part.size,
                "sha256": part.sha256,
                "plain_size": part.plain_size,
                "plain_sha256": part.plain_sha256,
            }
            for part in manifest.parts
        ],
        "notes": manifest.notes,
    }
    return json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"


def _bad(reason: str) -> BackupError:
    return BackupError(BackupErrorCode.integrity, f"manifest is invalid: {reason}")


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise _bad(key)
    return value


def _int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _bad(key)
    return value


def _parse_part(item: object) -> ManifestPart:
    if not isinstance(item, dict):
        raise _bad("part")
    part = ManifestPart(
        name=_text(item, "name"),
        size=_int(item, "size"),
        sha256=_text(item, "sha256"),
        plain_size=_int(item, "plain_size"),
        plain_sha256=_text(item, "plain_sha256"),
    )
    hashes_ok = _SHA.fullmatch(part.sha256) and _SHA.fullmatch(part.plain_sha256)
    if "/" in part.name or part.name.startswith(".") or not hashes_ok:
        raise _bad("part fields")
    return part


def _optional_text(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


def parse_manifest(data: bytes) -> Manifest:
    try:
        raw = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise _bad("not json") from exc
    if not isinstance(raw, dict):
        raise _bad("not an object")
    if raw.get("format") != MANIFEST_FORMAT:
        raise BackupError(BackupErrorCode.unsupported, f"backup format {raw.get('format')!r} is not supported")
    backup_id = _text(raw, "backup_id")
    enc = raw.get("encryption")
    parts_raw = raw.get("parts")
    if not is_backup_id(backup_id) or not isinstance(enc, dict) or not isinstance(parts_raw, list) or not parts_raw:
        raise _bad("backup_id, encryption or parts")
    try:
        mode = EncryptionMode(_text(enc, "mode"))
        created = datetime.fromisoformat(_text(raw, "created_at"))
    except ValueError as exc:
        raise _bad("mode or date") from exc
    notes = raw.get("notes")
    return Manifest(
        format=MANIFEST_FORMAT,
        backup_id=backup_id,
        created_at=created,
        app_version=_text(raw, "app_version"),
        schema_revision=_optional_text(raw, "schema_revision"),
        installation_id=_optional_text(raw, "installation_id"),
        encryption_mode=mode,
        salt_hex=_text(enc, "salt"),
        key_check=_text(enc, "key_check"),
        key_fingerprint=_optional_text(enc, "key_fingerprint"),
        parts=tuple(_parse_part(item) for item in parts_raw),
        notes={k: v for k, v in notes.items() if isinstance(v, (int, str))} if isinstance(notes, dict) else {},
    )


def manifest_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
