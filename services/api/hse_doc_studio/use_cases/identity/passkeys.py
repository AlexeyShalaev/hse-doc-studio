"""Passkey в профиле: список, регистрация нового ключа, переименование и удаление."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from hse_doc_studio.core.identity.entities import AuthTokenKind, MailKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.passkeys import (
    PASSKEY_LIMIT,
    CredentialJson,
    IPasskeyRepository,
    IWebAuthn,
    Passkey,
    PasskeyDescriptor,
    PasskeyFailure,
    PasskeyVerificationError,
    RelyingParty,
    clean_passkey_name,
    user_handle_of,
)
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    ICredentialRepository,
    ISessionRepository,
    IUserRepository,
)
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.mail.journal import MailOrigin, MailRefKind
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.mail import LinkDelivery
from hse_doc_studio.use_cases.identity.passkey_ceremony import PasskeyChallenges, PasskeyPolicy, require_recent_auth

DEFAULT_PASSKEY_NAME = "Passkey"


@dataclass(frozen=True)
class PasskeysView:
    items: list[Passkey]
    # Можно ли подтвердить личность паролем (у аккаунта есть пароль и вход по паролю включён).
    has_password: bool
    enabled: bool


def descriptors(passkeys: list[Passkey]) -> list[PasskeyDescriptor]:
    return [PasskeyDescriptor(p.credential_id, p.transports) for p in passkeys]


class LoginMethods:
    """Сколько способов войти останется у человека: пароль, внешние провайдеры, passkey."""

    def __init__(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        passkeys: IPasskeyRepository | None,
        settings: AuthSettingsService,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._passkeys = passkeys
        self._settings = settings

    async def has_password(self, user_id: str) -> bool:
        return (await self._settings.effective()).password_enabled and (
            await self._credentials.get_hash(user_id) is not None
        )

    async def remain(
        self, user_id: str, *, without_provider: str | None = None, without_passkey: str | None = None
    ) -> bool:
        """True, если без указанной привязки или ключа войти ещё можно. Вызывать под блокировкой строки человека."""
        if await self.has_password(user_id):
            return True
        if any(i.provider != without_provider for i in await self._users.list_identities(user_id)):
            return True
        if self._passkeys is None or not (await self._settings.effective()).passkeys_enabled:
            return False
        return any(p.id != without_passkey for p in await self._passkeys.list_for_user(user_id))


class ListPasskeysUC:
    def __init__(self, passkeys: IPasskeyRepository, methods: LoginMethods, policy: PasskeyPolicy) -> None:
        self._passkeys = passkeys
        self._methods = methods
        self._policy = policy

    async def execute(self, user_id: str) -> PasskeysView:
        return PasskeysView(
            items=await self._passkeys.list_for_user(user_id),
            has_password=await self._methods.has_password(user_id),
            enabled=await self._policy.enabled(),
        )


class StartPasskeyRegistrationUC:
    """Параметры для `navigator.credentials.create()`; уже зарегистрированные ключи исключаются."""

    def __init__(
        self,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        sessions: ISessionRepository,
        challenges: PasskeyChallenges,
        policy: PasskeyPolicy,
        webauthn: IWebAuthn,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._passkeys = passkeys
        self._sessions = sessions
        self._challenges = challenges
        self._policy = policy
        self._webauthn = webauthn
        self._clock = clock

    async def execute(self, user_id: str, session_id_hash: str | None, party: RelyingParty | None) -> dict[str, object]:
        party = await self._policy.require(party)
        await require_recent_auth(self._sessions, session_id_hash, user_id, self._clock())
        user = await self._users.get(user_id)
        if user is None or not user.can_sign_in:
            raise IdentityError(IdentityErrorCode.auth_required)
        existing = await self._passkeys.list_for_user(user_id)
        if len(existing) >= PASSKEY_LIMIT:
            raise IdentityError(IdentityErrorCode.passkey_limit)
        challenge = await self._challenges.issue(AuthTokenKind.passkey_register, user_id)
        return self._webauthn.registration_options(
            party,
            challenge=challenge,
            user_handle=user_handle_of(user.id),
            user_name=user.email,
            display_name=user.name or user.email,
            exclude=descriptors(existing),
        )


class FinishPasskeyRegistrationUC:
    """Проверка ответа браузера и сохранение ключа. Вызов должен быть выдан этому же человеку."""

    def __init__(
        self,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        challenges: PasskeyChallenges,
        policy: PasskeyPolicy,
        webauthn: IWebAuthn,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
        *,
        delivery: LinkDelivery | None = None,
    ) -> None:
        self._users = users
        self._passkeys = passkeys
        self._challenges = challenges
        self._policy = policy
        self._webauthn = webauthn
        self._audit = audit
        self._uow = uow
        self._clock = clock
        self._delivery = delivery

    async def execute(
        self,
        user_id: str,
        party: RelyingParty | None,
        credential: CredentialJson,
        *,
        name: str | None,
        fallback_name: str = DEFAULT_PASSKEY_NAME,
    ) -> Passkey:
        party = await self._policy.require(party)
        try:
            challenge = self._webauthn.registration_challenge(credential)
            token = await self._challenges.consume(AuthTokenKind.passkey_register, challenge)
            if token is None or token.user_id != user_id:
                raise PasskeyVerificationError(PasskeyFailure.challenge)
            created = self._webauthn.verify_registration(party, credential, challenge=challenge)
        except PasskeyVerificationError as failure:
            await self._audit.record(
                "auth.passkey_add_failed", actor_id=user_id, details={"reason": failure.reason.value}
            )
            raise IdentityError(IdentityErrorCode.passkey_invalid, status=422) from failure
        passkey = Passkey(
            id=uuid.uuid4().hex,
            user_id=user_id,
            credential_id=created.credential_id,
            public_key=created.public_key,
            sign_count=created.sign_count,
            rp_id=party.id,
            name=clean_passkey_name(name, fallback_name),
            created_at=self._clock(),
            transports=created.transports,
            aaguid=created.aaguid,
            backup_eligible=created.backup_eligible,
            backed_up=created.backed_up,
        )
        async with self._uow.begin():
            # Блокировка строки человека: две параллельные регистрации не обойдут предел.
            owner = await self._users.get_for_update(user_id)
            if owner is None:
                raise IdentityError(IdentityErrorCode.auth_required)
            if await self._passkeys.count_for_user(user_id) >= PASSKEY_LIMIT:
                raise IdentityError(IdentityErrorCode.passkey_limit)
            try:
                await self._passkeys.add(passkey)
            except PasskeyVerificationError as failure:
                raise IdentityError(IdentityErrorCode.passkey_invalid, status=409) from failure
            await self._audit.record(
                "auth.passkey_added",
                actor_id=user_id,
                target=passkey.id,
                details={"name": passkey.name, "synced": passkey.backup_eligible, "rp_id": passkey.rp_id},
            )
        # Письмо после записи: если ключ добавил не владелец (украденная сессия), он узнает об этом сразу.
        if self._delivery is not None:
            await self._delivery.notify(
                MailKind.passkey_added,
                owner.email,
                origin=MailOrigin.passkey_added,
                locale=owner.locale,
                params={"name": passkey.name},
                to_user_id=owner.id,
                ref_kind=MailRefKind.passkey,
                ref_id=passkey.id,
            )
        return passkey


class RenamePasskeyUC:
    def __init__(self, passkeys: IPasskeyRepository, audit: IAuditLog) -> None:
        self._passkeys = passkeys
        self._audit = audit

    async def execute(self, user_id: str, passkey_id: str, name: str) -> Passkey:
        cleaned = clean_passkey_name(name, "")
        if not cleaned:
            raise IdentityError(IdentityErrorCode.input_invalid)
        renamed = await self._passkeys.rename(user_id, passkey_id, cleaned)
        if renamed is None:
            raise IdentityError(IdentityErrorCode.not_found)
        await self._audit.record(
            "auth.passkey_renamed", actor_id=user_id, target=passkey_id, details={"name": renamed.name}
        )
        return renamed


class DeletePasskeyUC:
    """Удаление ключа: нужна свежая сессия; последний способ войти не удаляется."""

    def __init__(
        self,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        sessions: ISessionRepository,
        methods: LoginMethods,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._passkeys = passkeys
        self._sessions = sessions
        self._methods = methods
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, user_id: str, session_id_hash: str | None, passkey_id: str) -> None:
        await require_recent_auth(self._sessions, session_id_hash, user_id, self._clock())
        async with self._uow.begin():
            if await self._users.get_for_update(user_id) is None:
                raise IdentityError(IdentityErrorCode.not_found)
            target = next((p for p in await self._passkeys.list_for_user(user_id) if p.id == passkey_id), None)
            if target is None:
                raise IdentityError(IdentityErrorCode.not_found)
            if not await self._methods.remain(user_id, without_passkey=passkey_id):
                raise IdentityError(IdentityErrorCode.last_login_method)
            await self._passkeys.delete(user_id, passkey_id)
            await self._audit.record(
                "auth.passkey_removed", actor_id=user_id, target=passkey_id, details={"name": target.name}
            )
