"""Политика регистрации: кто и в каком состоянии получает аккаунт. Единственное место, где живут режимы."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.identity.entities import AuthSettings, RegistrationInvite, RegistrationMode, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import email_domain, is_valid_email, normalize_email


class RegistrationOutcome(StrEnum):
    """Что видит человек после отправки формы; ответ одинаков для нового и уже занятого адреса."""

    active = "active"
    check_email = "check_email"
    pending_approval = "pending_approval"


@dataclass(frozen=True)
class RegistrationDecision:
    status: UserStatus
    email_verified: bool
    # Нужен ли токен подтверждения почты (письмо или ссылка без SMTP).
    verification_token: bool
    outcome: RegistrationOutcome


def invite_usable(invite: RegistrationInvite, email: str, now: datetime) -> bool:
    """Приглашение не использовано, не просрочено и (если выписано на адрес) подходит этому адресу."""
    if invite.used_at is not None or invite.expires_at <= now:
        return False
    return invite.email is None or invite.email == normalize_email(email)


class RegistrationPolicy:
    """Режимы: open, domains, invite, closed и флаг одобрения. Действующее приглашение пускает в любом режиме.

    Без приглашения: подтверждение почты письмом, если есть SMTP; без SMTP аккаунт активен с неподтверждённой
    почтой, а ссылка подтверждения отдаётся на экране. Режим domains без SMTP не может проверить владение
    адресом, поэтому такие аккаунты ждут одобрения админа.
    """

    def __init__(self, settings: AuthSettings, *, smtp_enabled: bool) -> None:
        self._settings = settings
        self._smtp = smtp_enabled

    def evaluate(self, email: str, invite: RegistrationInvite | None = None) -> RegistrationDecision:
        if not is_valid_email(email):
            raise IdentityError(IdentityErrorCode.domain_not_allowed)
        if invite is not None:
            return self._invited(invite)
        self._ensure_open(email)
        needs_approval = self._settings.require_approval or (
            self._settings.registration_mode is RegistrationMode.domains and not self._smtp
        )
        if needs_approval:
            return RegistrationDecision(
                UserStatus.pending_approval, False, self._smtp, RegistrationOutcome.pending_approval
            )
        if self._smtp:
            return RegistrationDecision(UserStatus.pending_verification, False, True, RegistrationOutcome.check_email)
        return RegistrationDecision(UserStatus.active, False, True, RegistrationOutcome.check_email)

    def _invited(self, invite: RegistrationInvite) -> RegistrationDecision:
        # Приглашение на конкретный адрес само подтверждает почту: письмо с токеном дошло именно туда.
        if invite.email is not None:
            return RegistrationDecision(UserStatus.active, True, False, RegistrationOutcome.active)
        if self._smtp:
            return RegistrationDecision(UserStatus.pending_verification, False, True, RegistrationOutcome.check_email)
        return RegistrationDecision(UserStatus.active, False, True, RegistrationOutcome.check_email)

    def _ensure_open(self, email: str) -> None:
        mode = self._settings.registration_mode
        if mode is RegistrationMode.closed:
            raise IdentityError(IdentityErrorCode.registration_closed)
        if mode is RegistrationMode.invite:
            raise IdentityError(IdentityErrorCode.invitation_required)
        if mode is RegistrationMode.domains and email_domain(email) not in self._settings.registration_domains:
            raise IdentityError(IdentityErrorCode.domain_not_allowed)
