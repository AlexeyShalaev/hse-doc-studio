"""Профили подписантов в Postgres: одна строка на человека, картинка и ключ меняются независимо друг от друга."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.signatures.signer_profile import (
    ProfileImage,
    ProfilePublicKey,
    PublicKeyKind,
    SignerProfile,
)
from hse_doc_studio.core.value_objects import SignerInfo
from hse_doc_studio.infra.db.orm.signer_profiles import SignerProfileRow
from hse_doc_studio.infra.db.session import SessionProvider

_T = SignerProfileRow
# Всё, кроме байтов картинки: их читает только `read_image`.
_META = (
    _T.user_id,
    _T.image_sha256,
    func.octet_length(_T.image_png).label("image_size"),
    _T.image_width_px,
    _T.image_height_px,
    _T.image_updated_at,
    _T.key_kind,
    _T.key_data,
    _T.key_plate,
    _T.key_updated_at,
)
_IMAGE_NULL: Mapping[str, None] = {
    "image_png": None,
    "image_sha256": None,
    "image_width_px": None,
    "image_height_px": None,
    "image_updated_at": None,
}
_KEY_NULL: Mapping[str, None] = {"key_kind": None, "key_data": None, "key_plate": None, "key_updated_at": None}


class PostgresSignerProfileRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, user_id: str) -> SignerProfile:
        async with self._sessions.use() as session:
            row = (await session.execute(select(*_META).where(_T.user_id == user_id))).one_or_none()
        if row is None:
            return SignerProfile(user_id=user_id)
        image = None
        if row.image_sha256 is not None and row.image_updated_at is not None:
            image = ProfileImage(
                sha256=row.image_sha256,
                size=row.image_size or 0,
                width_px=row.image_width_px,
                height_px=row.image_height_px,
                updated_at=row.image_updated_at,
            )
        key = None
        if row.key_kind is not None and row.key_data is not None and row.key_plate is not None:
            key = ProfilePublicKey(
                kind=PublicKeyKind(row.key_kind),
                data=row.key_data,
                plate=_plate(row.key_plate),
                updated_at=row.key_updated_at or datetime.now(UTC),
            )
        return SignerProfile(user_id=user_id, image=image, public_key=key)

    async def read_image(self, user_id: str) -> bytes | None:
        async with self._sessions.use() as session:
            return (await session.execute(select(_T.image_png).where(_T.user_id == user_id))).scalar_one_or_none()

    async def save_image(self, user_id: str, png: bytes, image: ProfileImage) -> None:
        await self._upsert(
            user_id,
            {
                "image_png": png,
                "image_sha256": image.sha256,
                "image_width_px": image.width_px,
                "image_height_px": image.height_px,
                "image_updated_at": image.updated_at,
            },
        )

    async def clear_image(self, user_id: str) -> bool:
        return await self._clear(user_id, _T.image_png.is_not(None), _IMAGE_NULL)

    async def save_public_key(self, user_id: str, key: ProfilePublicKey) -> None:
        await self._upsert(
            user_id,
            {
                "key_kind": key.kind.value,
                "key_data": key.data,
                "key_plate": asdict(key.plate),
                "key_updated_at": key.updated_at,
            },
        )

    async def clear_public_key(self, user_id: str) -> bool:
        return await self._clear(user_id, _T.key_data.is_not(None), _KEY_NULL)

    async def _upsert(self, user_id: str, values: Mapping[str, object]) -> None:
        now = datetime.now(UTC)
        stmt = pg_insert(_T).values(user_id=user_id, updated_at=now, **values)
        stmt = stmt.on_conflict_do_update(index_elements=[_T.user_id], set_={**values, "updated_at": now})
        async with self._sessions.use() as session:
            await session.execute(stmt)

    async def _clear(self, user_id: str, present: Any, nulls: Mapping[str, None]) -> bool:
        """Обнуляет одну половину профиля; строка без картинки и без ключа удаляется."""
        async with self._sessions.use() as session:
            cleared = await session.execute(
                update(_T)
                .where(_T.user_id == user_id, present)
                .values(**nulls, updated_at=datetime.now(UTC))
                .returning(_T.user_id)
            )
            found = cleared.first() is not None
            await session.execute(
                delete(_T).where(and_(_T.user_id == user_id, _T.image_png.is_(None), _T.key_data.is_(None)))
            )
        return found


def _plate(raw: Mapping[str, Any]) -> SignerInfo:
    return SignerInfo(
        kind=str(raw.get("kind") or "manual"),
        owner=str(raw.get("owner") or ""),
        cert_id=str(raw.get("cert_id") or ""),
        valid_from=raw.get("valid_from"),
        valid_to=raw.get("valid_to"),
        signer_id=str(raw.get("signer_id") or ""),
        level=str(raw.get("level") or ""),
    )
