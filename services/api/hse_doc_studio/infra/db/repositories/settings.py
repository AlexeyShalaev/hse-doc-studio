"""Настройки в Postgres: ключи пользователя в user_settings, ключи установки в instance_settings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.context import ActorRequired, require_actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode, message_for
from hse_doc_studio.core.settings_scope import SETTING_SCOPES, SOURCE_ADMIN, SOURCE_ENV, SettingScope
from hse_doc_studio.infra.db.orm.identity import InstanceSettingRow, UserSettingRow
from hse_doc_studio.infra.db.session import SessionProvider

_INSTANCE_KEYS = frozenset(key for key, scope in SETTING_SCOPES.items() if scope is SettingScope.instance)


class PostgresSettingsRepository:
    """ISettingsRepository сервера: документ собирается из двух таблиц по области ключа.

    Ключ без записи в реестре областей считается пользовательским: чужим он стать не может.
    """

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self) -> dict[str, Any]:
        user_id = _user_id()
        async with self._sessions.use() as session:
            instance = (
                await session.execute(select(InstanceSettingRow).where(InstanceSettingRow.key.in_(_INSTANCE_KEYS)))
            ).scalars()
            own = (await session.execute(select(UserSettingRow).where(UserSettingRow.user_id == user_id))).scalars()
            return {**{row.key: row.value for row in own}, **{row.key: row.value for row in instance}}

    async def save(self, settings: dict[str, Any]) -> None:
        actor = require_actor()
        user_id = _user_id()
        wanted_instance = {key: value for key, value in settings.items() if key in _INSTANCE_KEYS}
        wanted_user = {key: value for key, value in settings.items() if key not in _INSTANCE_KEYS}
        async with self._sessions.use() as session:
            stored = {
                row.key: row
                for row in (
                    await session.execute(select(InstanceSettingRow).where(InstanceSettingRow.key.in_(_INSTANCE_KEYS)))
                ).scalars()
            }
            changed = {
                key
                for key in _INSTANCE_KEYS
                if (key in wanted_instance) != (key in stored)
                or (key in stored and stored[key].value != wanted_instance[key])
            }
            if changed and not actor.is_instance_admin:
                raise IdentityError(IdentityErrorCode.forbidden, message_for(IdentityErrorCode.forbidden))
            if locked := sorted(key for key in changed if key in stored and stored[key].source == SOURCE_ENV):
                raise IdentityError(
                    IdentityErrorCode.setting_locked,
                    f"{message_for(IdentityErrorCode.setting_locked)} ({', '.join(locked)})",
                )
            for key in sorted(changed):
                if key in wanted_instance:
                    stmt = pg_insert(InstanceSettingRow).values(
                        key=key, value=wanted_instance[key], source=SOURCE_ADMIN
                    )
                    await session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=[InstanceSettingRow.key],
                            set_={"value": stmt.excluded.value, "source": SOURCE_ADMIN, "updated_at": func.now()},
                        )
                    )
                else:
                    await session.execute(delete(InstanceSettingRow).where(InstanceSettingRow.key == key))
            await session.execute(
                delete(UserSettingRow).where(
                    UserSettingRow.user_id == user_id, UserSettingRow.key.not_in(wanted_user.keys())
                )
            )
            for key, value in wanted_user.items():
                stmt = pg_insert(UserSettingRow).values(user_id=user_id, key=key, value=value)
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[UserSettingRow.user_id, UserSettingRow.key],
                        set_={"value": stmt.excluded.value, "updated_at": func.now()},
                    )
                )


def _user_id() -> str:
    actor = require_actor()
    if actor.id is None:
        raise ActorRequired("у актора нет id пользователя")
    return actor.id
