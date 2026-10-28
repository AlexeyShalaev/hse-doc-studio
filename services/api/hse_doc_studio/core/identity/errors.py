"""Ошибки identity: закрытый список кодов и двуязычные сообщения.

Источник правды по кодам входа и аккаунта: contracts/server/error_codes.json. Тест сверяет его
с перечислением; сообщения на клиенте лежат в `errors:code.<код>`, здесь те же тексты для
ответов, которые строит сам бэкенд.
"""

from __future__ import annotations

from enum import StrEnum

from hse_doc_studio.core.i18n import localized_error


class IdentityErrorCode(StrEnum):
    invalid_credentials = "invalid_credentials"
    email_not_verified = "email_not_verified"
    pending_approval = "pending_approval"
    account_disabled = "account_disabled"
    registration_closed = "registration_closed"
    domain_not_allowed = "domain_not_allowed"
    invitation_required = "invitation_required"
    invitation_invalid = "invitation_invalid"
    rate_limited = "rate_limited"
    sso_login_required = "sso_login_required"
    csrf_failed = "csrf_failed"
    auth_required = "auth_required"
    forbidden = "forbidden"
    setup_token_invalid = "setup_token_invalid"  # noqa: S105 — код ошибки, не токен
    setup_already_done = "setup_already_done"
    password_policy = "password_policy"  # noqa: S105 — код ошибки, не пароль
    token_invalid = "token_invalid"  # noqa: S105 — код ошибки, не токен
    # Внутренние коды: наружу не отдаются как есть (нейтральные ответы), нужны use cases.
    email_taken = "email_taken"
    last_owner = "last_owner"
    slug_reserved = "slug_reserved"
    slug_invalid = "slug_invalid"


MESSAGES: dict[IdentityErrorCode, tuple[str, str]] = {
    IdentityErrorCode.invalid_credentials: ("Неверный e-mail или пароль.", "Wrong email or password."),
    IdentityErrorCode.email_not_verified: (
        "Подтвердите e-mail по ссылке из письма.",
        "Confirm your email using the link we sent.",
    ),
    IdentityErrorCode.pending_approval: (
        "Учётную запись должен одобрить администратор.",
        "An administrator has to approve your account.",
    ),
    IdentityErrorCode.account_disabled: ("Учётная запись отключена.", "This account is disabled."),
    IdentityErrorCode.registration_closed: ("Регистрация закрыта.", "Registration is closed."),
    IdentityErrorCode.domain_not_allowed: (
        "Регистрация с этого адреса недоступна.",
        "Registration is not available for this address.",
    ),
    IdentityErrorCode.invitation_required: (
        "Регистрация только по приглашению.",
        "Registration is by invitation only.",
    ),
    IdentityErrorCode.invitation_invalid: (
        "Приглашение недействительно или истекло.",
        "The invitation is invalid or has expired.",
    ),
    IdentityErrorCode.rate_limited: (
        "Слишком много попыток. Подождите и повторите.",
        "Too many attempts. Wait a moment and try again.",
    ),
    IdentityErrorCode.sso_login_required: (
        "Для этой учётной записи вход через единый вход.",
        "This account signs in with single sign-on.",
    ),
    IdentityErrorCode.csrf_failed: (
        "Сессия устарела. Обновите страницу и повторите.",
        "Your session is out of date. Reload the page and try again.",
    ),
    IdentityErrorCode.auth_required: ("Нужно войти.", "Sign in required."),
    IdentityErrorCode.forbidden: ("Недостаточно прав.", "You do not have permission."),
    IdentityErrorCode.setup_token_invalid: ("Неверный токен установки.", "The setup token is wrong."),
    IdentityErrorCode.setup_already_done: ("Первый запуск уже выполнен.", "First-run setup is already done."),
    IdentityErrorCode.password_policy: (
        "Пароль не подходит под требования.",
        "The password does not meet the requirements.",
    ),
    IdentityErrorCode.token_invalid: ("Ссылка недействительна или истекла.", "The link is invalid or has expired."),
    IdentityErrorCode.email_taken: ("Этот e-mail уже занят.", "This email is already taken."),
    IdentityErrorCode.last_owner: ("Нельзя убрать последнего владельца.", "The last owner cannot be removed."),
    IdentityErrorCode.slug_reserved: ("Это имя зарезервировано.", "This name is reserved."),
    IdentityErrorCode.slug_invalid: (
        "Допустимы строчные латинские буквы, цифры и дефис.",
        "Use lowercase Latin letters, digits and hyphens.",
    ),
}


def message_for(code: IdentityErrorCode) -> str:
    ru, en = MESSAGES[code]
    return localized_error(ru, en)


class IdentityError(Exception):
    """Ошибка identity с кодом из закрытого списка; `detail` уже локализован."""

    def __init__(self, code: IdentityErrorCode, detail: str = "", *, retry_after_s: int | None = None) -> None:
        detail = detail or message_for(code)
        super().__init__(detail)
        self.code = code
        self.detail = detail
        # Для rate_limited: через сколько секунд повторить (заголовок Retry-After).
        self.retry_after_s = retry_after_s
