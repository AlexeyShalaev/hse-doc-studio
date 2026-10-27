"""Перешифровка секретов в базе под первичный ключ: шаг смены ключа после добавления прежнего в RETIRED_KEYS.

Запись идёт только если значение не изменилось с чтения; параллельная запись нового секрета не затирается, но
команду всё равно запускают при остановленном приложении.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.secrets import EncryptedColumn, EncryptedColumnRegistry
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher

logger = structlog.get_logger()


@dataclass
class ReencryptReport:
    updated: int = 0
    current: int = 0
    # Строки, которые не открылись ни одним ключом: их перешифровать нечем, значения не тронуты.
    unreadable: list[str] = field(default_factory=list)
    # Строки, изменённые за время работы команды: их не трогали, запустите команду ещё раз.
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unreadable and not self.skipped


async def reencrypt_all(
    engine: AsyncEngine,
    cipher: FernetSecretCipher,
    registry: EncryptedColumnRegistry,
    *,
    dry_run: bool = False,
) -> ReencryptReport:
    report = ReencryptReport()
    for column in registry.all():
        await _reencrypt_column(engine, cipher, column, report, dry_run=dry_run)
    return report


async def _reencrypt_column(
    engine: AsyncEngine,
    cipher: FernetSecretCipher,
    column: EncryptedColumn,
    report: ReencryptReport,
    *,
    dry_run: bool,
) -> None:
    # Идентификаторы берутся только из реестра в коде, не из ввода.
    select = text(f'SELECT "{column.pk}", "{column.column}" FROM "{column.table}" WHERE "{column.column}" IS NOT NULL')  # noqa: S608
    update = text(
        f'UPDATE "{column.table}" SET "{column.column}" = :value '  # noqa: S608
        f'WHERE "{column.pk}" = :pk AND "{column.column}" = :old'
    )
    async with engine.begin() as conn:
        rows = (await conn.execute(select)).all()
        for pk, token in rows:
            legacy = column.legacy_aad(str(pk)) if column.legacy_aad else None
            try:
                secret = cipher.decrypt(token, aad=column.aad(pk), legacy_aad=legacy)
            except GitSyncError:
                report.unreadable.append(f"{column.label}#{pk}")
                logger.warning("secret cannot be reencrypted", column=column.label)
                continue
            if cipher.is_current(token) and _bound_to(cipher, token, column, pk):
                report.current += 1
                continue
            report.updated += 1
            if not dry_run:
                result = await conn.execute(
                    update, {"value": cipher.encrypt(secret, aad=column.aad(pk)), "pk": pk, "old": token}
                )
                if result.rowcount == 0:
                    report.updated -= 1
                    report.skipped.append(f"{column.label}#{pk}")


def _bound_to(cipher: FernetSecretCipher, token: str, column: EncryptedColumn, pk: object) -> bool:
    """Привязан ли шифртекст по текущей схеме: записи со старой привязкой тоже переписываются."""
    try:
        cipher.decrypt(token, aad=column.aad(pk))
    except GitSyncError:
        return False
    return True
