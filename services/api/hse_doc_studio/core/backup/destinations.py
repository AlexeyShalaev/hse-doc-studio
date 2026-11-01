"""Проверка ввода назначения и сборка ключей объектов бэкапа."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from hse_doc_studio.core.backup.entities import DestinationKind, DestinationSpec
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode

NAME_MAX = 128
_BUCKET = re.compile(r"[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]")
_PREFIX_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\- ]*")


def _bad(field: str, text: str) -> BackupError:
    return BackupError(BackupErrorCode.invalid_input, text, field=field)


def normalize_prefix(prefix: str) -> str:
    """Префикс без краевых косых; сегменты только из безопасных символов, без `..` и скрытых имён."""
    cleaned = prefix.strip().strip("/")
    if not cleaned:
        return ""
    for segment in cleaned.split("/"):
        if not _PREFIX_SEGMENT.fullmatch(segment) or segment in {".", ".."} or len(segment) > 128:  # noqa: PLR2004
            raise _bad("prefix", "prefix contains an unsafe segment")
    return cleaned


def normalize_local_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/").strip("/")
    if not cleaned:
        raise _bad("local_path", "local path is required")
    for segment in cleaned.split("/"):
        if not _PREFIX_SEGMENT.fullmatch(segment) or segment in {".", ".."}:
            raise _bad("local_path", "path must be inside the local root and without '..'")
    return cleaned


def validate_spec(spec: DestinationSpec) -> DestinationSpec:
    """Нормализованная копия или `BackupError` с названием поля."""
    name = spec.name.strip()
    if not name or len(name) > NAME_MAX:
        raise _bad("name", "name is required (up to 128 characters)")
    if spec.kind is DestinationKind.local:
        return DestinationSpec(name=name, kind=spec.kind, local_path=normalize_local_path(spec.local_path or ""))
    bucket = (spec.bucket or "").strip()
    if not _BUCKET.fullmatch(bucket):
        raise _bad("bucket", "bucket name is invalid")
    endpoint = (spec.endpoint or "").strip() or None
    if endpoint is not None:
        parts = urlsplit(endpoint)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise _bad("endpoint", "endpoint must be an http(s) address without credentials")
        endpoint = endpoint.rstrip("/")
    region = spec.region.strip() or "us-east-1"
    if len(region) > 64:  # noqa: PLR2004
        raise _bad("region", "region is too long")
    return DestinationSpec(
        name=name,
        kind=spec.kind,
        endpoint=endpoint,
        region=region,
        bucket=bucket,
        prefix=normalize_prefix(spec.prefix),
        path_style=spec.path_style,
    )


def object_key(prefix: str, *parts: str) -> str:
    return "/".join(p for p in (prefix.strip("/"), *parts) if p)


def key_hint(access_key: str | None) -> str | None:
    """Подсказка о ключе доступа для списка: последние четыре символа."""
    if not access_key:
        return None
    return "…" + access_key[-4:] if len(access_key) > 4 else "…"  # noqa: PLR2004
