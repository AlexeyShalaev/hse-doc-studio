"""Регистрация по приглашению сразу с passkey, без пароля.

Только приглашение на конкретный адрес: оно само подтверждает почту (письмо с токеном дошло туда), поэтому аккаунт
активен сразу и вход открывается тем же ответом. Приглашение «на любой адрес» почту не подтверждает: там остаётся
регистрация с паролем и письмом подтверждения. Режим регистрации не важен, приглашение пускает в любом.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from hse_doc_studio.core.identity.entities import AuthTokenKind, RegistrationInvite, Session, User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, new_token, normalize_email
from hse_doc_studio.core.identity.passkeys import (
    CredentialJson,
    IPasskeyRepository,
    IWebAuthn,
    Passkey,
    PasskeyFailure,
    PasskeyVerificationError,
    RelyingParty,
    clean_passkey_name,
    user_handle_of,
)
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    IRegistrationInviteRepository,
    ISessionRepository,
    IUserRepository,
)
from hse_doc_studio.core.identity.registration import invite_usable
from hse_doc_studio.core.identity.session_policy import Clock, SessionPolicy, utc_now
from hse_doc_studio.core.invitations.protocols import IEmailVerifiedHook
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.login import LoginResult
from hse_doc_studio.use_cases.identity.passkey_ceremony import PasskeyChallenges, PasskeyPolicy
from hse_doc_studio.use_cases.identity.passkeys import DEFAULT_PASSKEY_NAME
from hse_doc_studio.use_cases.identity.sessions import session_deadline


def _payload(invite: RegistrationInvite, user_id: str) -> str:
    return f"{invite.id}:{user_id}"


async def address_invite(
    invites: IRegistrationInviteRepository, users: IUserRepository, token: str, clock: Clock
) -> RegistrationInvite:
    """Годное приглашение на адрес, у которого ещё нет аккаунта.

    Занятый адрес называется прямо (`email_taken`): токен из письма доказывает, что спрашивает владелец ящика.
    """
    invite = await invites.get(hash_token(token))
    if invite is None or invite.email is None or not invite_usable(invite, invite.email, clock()):
        raise IdentityError(IdentityErrorCode.invitation_invalid)
    if await users.get_by_email(invite.email) is not None:
        raise IdentityError(IdentityErrorCode.email_taken)
    return invite


class StartPasskeySignupUC:
    """Параметры `navigator.credentials.create()` для будущего аккаунта: его id выбирается сейчас и лежит в вызове."""

    def __init__(
        self,
        invites: IRegistrationInviteRepository,
        users: IUserRepository,
        challenges: PasskeyChallenges,
        policy: PasskeyPolicy,
        webauthn: IWebAuthn,
        clock: Clock = utc_now,
    ) -> None:
        self._invites = invites
        self._users = users
        self._challenges = challenges
        self._policy = policy
        self._webauthn = webauthn
        self._clock = clock

    async def execute(self, party: RelyingParty | None, invitation_token: str, name: str) -> dict[str, object]:
        party = await self._policy.require(party)
        invite = await address_invite(self._invites, self._users, invitation_token, self._clock)
        assert invite.email is not None  # noqa: S101 — address_invite пропускает только приглашения на адрес
        user_id = uuid.uuid4().hex
        challenge = await self._challenges.issue(AuthTokenKind.passkey_signup, None, payload=_payload(invite, user_id))
        return self._webauthn.registration_options(
            party,
            challenge=challenge,
            user_handle=user_handle_of(user_id),
            user_name=invite.email,
            display_name=name.strip() or invite.email,
            exclude=[],
        )


class FinishPasskeySignupUC:
    """Проверенный ответ браузера создаёт аккаунт без пароля, гасит приглашение, сохраняет ключ и открывает сессию."""

    def __init__(
        self,
        invites: IRegistrationInviteRepository,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        sessions: ISessionRepository,
        challenges: PasskeyChallenges,
        policy: PasskeyPolicy,
        webauthn: IWebAuthn,
        audit: IAuditLog,
        uow: IUnitOfWork,
        session_policy: SessionPolicy | None = None,
        clock: Clock = utc_now,
        *,
        email_hook: IEmailVerifiedHook | None = None,
    ) -> None:
        self._invites = invites
        self._users = users
        self._passkeys = passkeys
        self._sessions = sessions
        self._challenges = challenges
        self._policy = policy
        self._webauthn = webauthn
        self._audit = audit
        self._uow = uow
        self._session_policy = session_policy or SessionPolicy()
        self._clock = clock
        self._email_hook = email_hook

    async def execute(
        self,
        party: RelyingParty | None,
        invitation_token: str,
        name: str,
        credential: CredentialJson,
        *,
        passkey_name: str | None = None,
        locale: str | None = None,
        ip: str | None = None,
        user_agent: str = "",
    ) -> LoginResult:
        party = await self._policy.require(party)
        invite = await address_invite(self._invites, self._users, invitation_token, self._clock)
        assert invite.email is not None  # noqa: S101 — address_invite пропускает только приглашения на адрес
        try:
            challenge = self._webauthn.registration_challenge(credential)
            token = await self._challenges.consume(AuthTokenKind.passkey_signup, challenge)
            invite_id, _, user_id = (token.payload or "").partition(":") if token else ("", "", "")
            if token is None or invite_id != invite.id or not user_id:
                raise PasskeyVerificationError(PasskeyFailure.challenge)
            created = self._webauthn.verify_registration(party, credential, challenge=challenge)
        except PasskeyVerificationError as failure:
            await self._audit.record(
                "auth.passkey_signup_failed", actor_id=None, details={"ip": ip, "reason": failure.reason.value}
            )
            raise IdentityError(IdentityErrorCode.passkey_invalid, status=422) from failure

        now = self._clock()
        email = invite.email
        user = User(
            id=user_id,
            email=email,
            email_normalized=normalize_email(email),
            name=name.strip() or normalize_email(email).partition("@")[0],
            # Приглашение на адрес подтверждает почту, как и при регистрации с паролем: аккаунт активен сразу.
            status=UserStatus.active,
            created_at=now,
            email_verified=True,
            locale=locale if locale in ("ru", "en") else None,
            last_login_at=now,
        )
        passkey = Passkey(
            id=uuid.uuid4().hex,
            user_id=user.id,
            credential_id=created.credential_id,
            public_key=created.public_key,
            sign_count=created.sign_count,
            rp_id=party.id,
            name=clean_passkey_name(passkey_name, DEFAULT_PASSKEY_NAME),
            created_at=now,
            transports=created.transports,
            aaguid=created.aaguid,
            backup_eligible=created.backup_eligible,
            backed_up=created.backed_up,
        )
        secret = new_token()
        session = Session(
            id_hash=hash_token(secret),
            user_id=user.id,
            csrf_token=new_token(),
            created_at=now,
            last_seen_at=now,
            expires_at=now,
            ip=ip,
            user_agent=user_agent[:512],
        )
        session = replace(session, expires_at=session_deadline(session, self._session_policy, now))
        async with self._uow.begin():
            await self._users.add(user)
            if await self._invites.consume(invite.token_hash, email, now) is None:
                raise IdentityError(IdentityErrorCode.invitation_invalid)
            try:
                await self._passkeys.add(passkey)
            except PasskeyVerificationError as failure:
                raise IdentityError(IdentityErrorCode.passkey_invalid, status=409) from failure
            await self._sessions.add(session)
            await self._audit.record(
                "auth.register",
                actor_id=user.id,
                details={"status": user.status.value, "invite": invite.id, "method": "passkey"},
            )
            await self._audit.record(
                "auth.passkey_added",
                actor_id=user.id,
                target=passkey.id,
                details={"name": passkey.name, "synced": passkey.backup_eligible, "rp_id": passkey.rp_id},
            )
            await self._audit.record("auth.login", actor_id=user.id, details={"ip": ip, "method": "passkey"})
        if self._email_hook is not None:
            await self._email_hook.on_email_verified(user.id, user.email_normalized)
        return LoginResult(user=user, session=session, secret=secret)
