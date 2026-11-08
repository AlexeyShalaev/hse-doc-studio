"""Ключ подписи по умолчанию из профиля пользователя: им подписывается комплект и заполняется плашка.

Хранится в настройках пользователя (сервер: `user_settings`, локально: config.json) только идентификатором ключа.
Если ключ один, он выбирается сам. Пароль ключа здесь не хранится никогда.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository, ISigningIdentityRepository

DEFAULT_KEY_SETTING = "signing_default_identity_id"


@dataclass(frozen=True)
class DefaultKey:
    # Выбранный явно ключ (None: не выбран или удалён).
    chosen_id: UUID | None
    # Ключ, которым подпишет «Подписать комплект»: выбранный, а без выбора единственный.
    effective: SigningIdentity | None

    @property
    def auto(self) -> bool:
        return self.chosen_id is None and self.effective is not None


class DefaultSigningKey:
    def __init__(self, settings: ISettingsRepository, identities: ISigningIdentityRepository) -> None:
        self._settings = settings
        self._identities = identities

    async def get(self) -> DefaultKey:
        identities = await self._identities.list_all()
        raw = (await self._settings.get()).get(DEFAULT_KEY_SETTING)
        chosen = next((i for i in identities if str(i.id) == raw), None) if isinstance(raw, str) else None
        if chosen is not None:
            return DefaultKey(chosen.id, chosen)
        return DefaultKey(None, identities[0] if len(identities) == 1 else None)

    async def resolve(self, identity_id: UUID | None) -> SigningIdentity | None:
        """Ключ для подписи: явно переданный, иначе ключ по умолчанию."""
        if identity_id is None:
            return (await self.get()).effective
        identity = await self._identities.get(identity_id)
        if identity is None:
            raise NotFoundError(
                localized_error(f"Ключ подписи {identity_id} не найден", f"Signing key {identity_id} not found")
            )
        return identity

    async def set(self, identity_id: UUID | None) -> DefaultKey:
        if identity_id is not None and await self._identities.get(identity_id) is None:
            raise NotFoundError(
                localized_error(f"Ключ подписи {identity_id} не найден", f"Signing key {identity_id} not found")
            )
        current = dict(await self._settings.get())
        if identity_id is None:
            current.pop(DEFAULT_KEY_SETTING, None)
        else:
            current[DEFAULT_KEY_SETTING] = str(identity_id)
        await self._settings.save(current)
        return await self.get()
