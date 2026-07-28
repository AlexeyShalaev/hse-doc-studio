from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind

logger = structlog.get_logger()

_FILENAME = "signing_identities.json"
_KEYS_DIR = "signing_keys"


class JsonSigningIdentityRepository:
    """Persists signing identity metadata to data_dir/signing_identities.json.

    Key material (PEM cert + key) lives in data_dir/signing_keys/<id>/.
    Mirrors JsonAIProviderRepository: atomic writes, graceful corrupt-record
    handling, APP-scope (one instance for the process lifetime).
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / _FILENAME
        self._keys_root = data_dir / _KEYS_DIR

    # ── public API (ISigningIdentityRepository protocol) ─────────────────────

    def list_all(self) -> list[SigningIdentity]:
        return self._load()

    def get(self, identity_id: UUID) -> SigningIdentity | None:
        for item in self._load():
            if item.id == identity_id:
                return item
        return None

    def create(self, identity: SigningIdentity) -> None:
        records = self._load()
        records.append(identity)
        self._save(records)

    def delete(self, identity_id: UUID) -> bool:
        records = self._load()
        before = len(records)
        records = [r for r in records if r.id != identity_id]
        if len(records) == before:
            return False
        self._save(records)
        return True

    def key_dir(self, identity_id: UUID) -> Path:
        """Return (and create) the directory that holds key material for this identity."""
        d = self._keys_root / str(identity_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── internal ─────────────────────────────────────────────────────────────

    def _load(self) -> list[SigningIdentity]:
        if not self._path.exists():
            return []
        try:
            raw: list[dict[str, Any]] = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("signing_identities.json read error", exc=str(exc))
            return []
        results: list[SigningIdentity] = []
        for record in raw:
            try:
                results.append(self._from_dict(record))
            except Exception as exc:
                logger.warning("signing_identity: skipping malformed record", exc=str(exc), record=record)
        return results

    def _save(self, records: list[SigningIdentity]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = json.dumps([self._to_dict(r) for r in records], ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._data_dir, prefix=".si_tmp_")
        try:
            os.write(fd, data.encode())
            os.close(fd)
            os.replace(tmp, self._path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    @staticmethod
    def _to_dict(r: SigningIdentity) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "label": r.label,
            "kind": r.kind.value,
            "subject_cn": r.subject_cn,
            "not_after": r.not_after.isoformat(),
            "trusted": r.trusted,
            "created_at": r.created_at.isoformat(),
        }

    @staticmethod
    def _from_dict(d: dict[str, Any]) -> SigningIdentity:
        return SigningIdentity(
            id=UUID(d["id"]),
            label=d["label"],
            kind=SigningIdentityKind(d["kind"]),
            subject_cn=d["subject_cn"],
            not_after=datetime.fromisoformat(d["not_after"]).replace(tzinfo=timezone.utc),
            trusted=bool(d.get("trusted", False)),
            created_at=datetime.fromisoformat(d["created_at"]).replace(tzinfo=timezone.utc),
        )
