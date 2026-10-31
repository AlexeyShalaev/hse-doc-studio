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
    forbidden_role = "forbidden_role"
    not_found = "not_found"
    setup_token_invalid = "setup_token_invalid"  # noqa: S105 — код ошибки, не токен
    setup_already_done = "setup_already_done"
    password_policy = "password_policy"  # noqa: S105 — код ошибки, не пароль
    token_invalid = "token_invalid"  # noqa: S105 — код ошибки, не токен
    setup_required = "setup_required"
    # Внутренние коды: наружу не отдаются как есть (нейтральные ответы), нужны use cases.
    email_taken = "email_taken"
    last_owner = "last_owner"
    last_admin = "last_admin"
    slug_reserved = "slug_reserved"
    slug_invalid = "slug_invalid"
    setting_locked = "setting_locked"
    last_login_method = "last_login_method"
    input_invalid = "input_invalid"
    slug_taken = "slug_taken"
    org_has_projects = "org_has_projects"
    name_taken = "name_taken"
    already_member = "already_member"
    user_not_found = "user_not_found"
    user_has_projects = "user_has_projects"
    user_not_disabled = "user_not_disabled"
    # Личные раннеры: выключены в установке, предел, отозван, проект без личного владельца, сопряжение.
    personal_runners_disabled = "personal_runners_disabled"
    personal_runner_limit = "personal_runner_limit"
    runner_revoked = "runner_revoked"
    runner_paused_by_admin = "runner_paused_by_admin"
    project_not_personal = "project_not_personal"
    runner_pairing_invalid = "runner_pairing_invalid"
    runner_pairing_expired = "runner_pairing_expired"
    runner_pairing_used = "runner_pairing_used"
    # ИИ через свой раннер и локальная Студия как раннер.
    relay_unavailable = "relay_unavailable"
    relay_busy = "relay_busy"
    ai_provider_runner_invalid = "ai_provider_runner_invalid"
    remote_runner_url_invalid = "remote_runner_url_invalid"
    remote_runner_unreachable = "remote_runner_unreachable"
    remote_runner_disabled = "remote_runner_disabled"
    # Ссылки доступа и гости.
    links_disabled = "links_disabled"
    link_limit = "link_limit"
    link_role_too_high = "link_role_too_high"
    link_password_invalid = "link_password_invalid"  # noqa: S105 — код ошибки, не пароль
    link_revoked = "link_revoked"
    link_login_required = "link_login_required"
    link_password_wrong = "link_password_wrong"  # noqa: S105 — код ошибки, не пароль
    link_password_locked = "link_password_locked"  # noqa: S105 — код ошибки, не пароль
    link_org_only = "link_org_only"
    link_inactive = "link_inactive"
    guest_name_required = "guest_name_required"
    guest_build_unavailable = "guest_build_unavailable"
    # invites: приглашения в проект, запросы доступа, передача владения.
    invitation_pending = "invitation_pending"
    invitation_limit = "invitation_limit"
    external_invite_forbidden = "external_invite_forbidden"
    invitee_cannot_register = "invitee_cannot_register"
    invitation_role_too_high = "invitation_role_too_high"
    persona_unknown = "persona_unknown"
    invitation_not_pending = "invitation_not_pending"
    invitation_resend_too_soon = "invitation_resend_too_soon"
    invitation_expired = "invitation_expired"
    invitation_email_mismatch = "invitation_email_mismatch"
    access_request_decided = "access_request_decided"
    confirm_name_mismatch = "confirm_name_mismatch"
    transfer_expired = "transfer_expired"
    transfer_outdated = "transfer_outdated"
    # Сервер как git-remote: git по HTTPS, вход устройства по коду, вход локальной Студии на сервер.
    git_scope_missing = "git_scope_missing"
    git_busy = "git_busy"
    git_project_busy = "git_project_busy"
    device_scope_invalid = "device_scope_invalid"
    device_code_invalid = "device_code_invalid"
    device_code_expired = "device_code_expired"
    device_code_used = "device_code_used"
    git_server_url_invalid = "git_server_url_invalid"
    git_server_not_studio = "git_server_not_studio"
    git_server_unreachable = "git_server_unreachable"


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
    IdentityErrorCode.forbidden_role: ("Недостаточно прав на проекте.", "You do not have the role this needs."),
    IdentityErrorCode.not_found: ("Не найдено или нет доступа.", "Not found or no access."),
    IdentityErrorCode.setup_token_invalid: ("Неверный токен установки.", "The setup token is wrong."),
    IdentityErrorCode.setup_already_done: ("Первый запуск уже выполнен.", "First-run setup is already done."),
    IdentityErrorCode.password_policy: (
        "Пароль не подходит под требования.",
        "The password does not meet the requirements.",
    ),
    IdentityErrorCode.token_invalid: ("Ссылка недействительна или истекла.", "The link is invalid or has expired."),
    IdentityErrorCode.setup_required: (
        "Сервер ещё настраивается. Подождите, пока администратор завершит первый запуск.",
        "The server is still being set up. Wait until the administrator finishes the first run.",
    ),
    IdentityErrorCode.email_taken: ("Этот e-mail уже занят.", "This email is already taken."),
    IdentityErrorCode.last_owner: ("Нельзя убрать последнего владельца.", "The last owner cannot be removed."),
    IdentityErrorCode.last_admin: (
        "Нельзя лишить установку последнего администратора.",
        "The installation cannot be left without an administrator.",
    ),
    IdentityErrorCode.slug_reserved: ("Это имя зарезервировано.", "This name is reserved."),
    IdentityErrorCode.slug_invalid: (
        "Допустимы строчные латинские буквы, цифры и дефис.",
        "Use lowercase Latin letters, digits and hyphens.",
    ),
    IdentityErrorCode.setting_locked: (
        "Значение задано через окружение и не меняется из интерфейса.",
        "This value is set by the environment and cannot be changed here.",
    ),
    IdentityErrorCode.last_login_method: (
        "Нельзя выключить последний способ входа: останется вход, которым никто не сможет воспользоваться.",
        "The last way to sign in cannot be turned off: nobody would be able to sign in.",
    ),
    IdentityErrorCode.input_invalid: ("Некорректные данные.", "Invalid input."),
    IdentityErrorCode.slug_taken: (
        "Этот адрес организации уже занят.",
        "This organization address is already taken.",
    ),
    IdentityErrorCode.org_has_projects: (
        "В организации есть проекты: сначала передайте или удалите их.",
        "The organization still has projects: move or delete them first.",
    ),
    IdentityErrorCode.name_taken: (
        "Такое название уже есть.",
        "This name is already in use.",
    ),
    IdentityErrorCode.already_member: (
        "Человек уже состоит здесь.",
        "This person is already a member.",
    ),
    IdentityErrorCode.user_not_found: (
        "Пользователь не найден.",
        "User not found.",
    ),
    IdentityErrorCode.user_has_projects: (
        "У человека остались проекты или организации, где он единственный владелец: сначала удалите или передайте их.",
        "This person is still the only owner of projects or organizations: delete or hand them over first.",
    ),
    IdentityErrorCode.user_not_disabled: (
        "Сначала отключите учётную запись: удалить можно только отключённую.",
        "Disable the account first: only a disabled account can be deleted.",
    ),
    IdentityErrorCode.personal_runners_disabled: (
        "Администратор выключил личные раннеры.",
        "The administrator turned personal runners off.",
    ),
    IdentityErrorCode.personal_runner_limit: (
        "Достигнут предел личных раннеров или токенов. Отзовите ненужный.",
        "You've reached the limit of personal runners or tokens. Revoke one you no longer need.",
    ),
    IdentityErrorCode.runner_revoked: ("Раннер отозван.", "The runner has been revoked."),
    IdentityErrorCode.runner_paused_by_admin: (
        "Раннер приостановил администратор: снять паузу может только он.",
        "An administrator paused this runner: only an administrator can resume it.",
    ),
    IdentityErrorCode.project_not_personal: (
        "Это проект организации: сборки идут на общих раннерах.",
        "This is an organization project: builds use shared runners.",
    ),
    IdentityErrorCode.runner_pairing_invalid: (
        "Код не найден. Проверьте его в Студии.",
        "Code not found. Check it in the Studio.",
    ),
    IdentityErrorCode.runner_pairing_expired: (
        "Код истёк. Начните подключение в Студии заново.",
        "The code has expired. Start connecting from the Studio again.",
    ),
    IdentityErrorCode.runner_pairing_used: ("Код уже использован.", "The code has already been used."),
    IdentityErrorCode.relay_unavailable: (
        "Раннер не ответил. Запустите его или выберите другую модель.",
        "The runner didn't respond. Start it or choose another model.",
    ),
    IdentityErrorCode.relay_busy: (
        "Слишком много запросов к раннеру одновременно, попробуйте через минуту.",
        "Too many requests to the runner at once, try again in a minute.",
    ),
    IdentityErrorCode.ai_provider_runner_invalid: (
        "Выберите свой раннер и объявленный им ИИ-адрес.",
        "Choose your own runner and an AI endpoint it declares.",
    ),
    IdentityErrorCode.remote_runner_url_invalid: (
        "Адрес сервера должен начинаться с https:// (http только для localhost).",
        "The server address must start with https:// (http only for localhost).",
    ),
    IdentityErrorCode.remote_runner_unreachable: (
        "Сервер не отвечает. Проверьте адрес и сеть.",
        "The server isn't responding. Check the address and the network.",
    ),
    IdentityErrorCode.remote_runner_disabled: (
        "На сервере выключены личные раннеры.",
        "Personal runners are turned off on the server.",
    ),
    IdentityErrorCode.links_disabled: (
        "Ссылки на проекты выключены.",
        "Project links are turned off.",
    ),
    IdentityErrorCode.link_limit: (
        "Не больше 50 действующих ссылок на проект.",
        "A project can have at most 50 active links.",
    ),
    IdentityErrorCode.link_role_too_high: (
        "Роль ссылки выше допустимой.",
        "The link role is higher than allowed.",
    ),
    IdentityErrorCode.link_password_invalid: (
        "Пароль ссылки должен быть от 8 до 128 символов.",
        "A link password must be 8 to 128 characters long.",
    ),
    IdentityErrorCode.link_revoked: (
        "Ссылка уже отозвана.",
        "The link has already been revoked.",
    ),
    IdentityErrorCode.link_login_required: (
        "Чтобы открыть ссылку, войдите.",
        "Sign in to open this link.",
    ),
    IdentityErrorCode.link_password_wrong: (
        "Неверный пароль.",
        "Wrong password.",
    ),
    IdentityErrorCode.link_password_locked: (
        "Слишком много попыток. Попробуйте позже.",
        "Too many attempts. Try again later.",
    ),
    IdentityErrorCode.link_org_only: (
        "Ссылка только для участников организации.",
        "This link is for organization members only.",
    ),
    IdentityErrorCode.link_inactive: (
        "Ссылка не действует.",
        "The link is no longer valid.",
    ),
    IdentityErrorCode.guest_name_required: (
        "Введите имя.",
        "Enter your name.",
    ),
    IdentityErrorCode.guest_build_unavailable: (
        "Сборка по этой ссылке недоступна.",
        "Builds are not available through this link.",
    ),
    # invites
    IdentityErrorCode.invitation_pending: (
        "Этому человеку уже отправлено приглашение.",
        "This person already has a pending invitation.",
    ),
    IdentityErrorCode.invitation_limit: (
        "Не больше 50 ожидающих приглашений в проект.",
        "A project can have at most 50 pending invitations.",
    ),
    IdentityErrorCode.external_invite_forbidden: (
        "Организация запретила приглашать людей с чужих доменов.",
        "The organization does not allow inviting people from other domains.",
    ),
    IdentityErrorCode.invitee_cannot_register: (
        "Регистрация на сервере выключена: у этого адреса нет аккаунта, и создать его нельзя.",
        "Sign-up is turned off on this server: this address has no account and cannot get one.",
    ),
    IdentityErrorCode.invitation_role_too_high: (
        "Нельзя выдать роль или права выше своих.",
        "You cannot grant a role or rights above your own.",
    ),
    IdentityErrorCode.persona_unknown: (
        "Такой персоны нет в проекте.",
        "This persona does not exist in the project.",
    ),
    IdentityErrorCode.invitation_not_pending: (
        "Приглашение уже принято, отклонено или отозвано.",
        "The invitation has already been accepted, declined or revoked.",
    ),
    IdentityErrorCode.invitation_resend_too_soon: (
        "Повторно отправить можно не чаще раза в 10 минут и не больше 5 раз.",
        "You can resend at most once every 10 minutes and no more than 5 times.",
    ),
    IdentityErrorCode.invitation_expired: (
        "Срок приглашения истёк. Попросите прислать новое.",
        "The invitation has expired. Ask for a new one.",
    ),
    IdentityErrorCode.invitation_email_mismatch: (
        "Приглашение отправлено на другой адрес. Войдите тем аккаунтом, на чью почту оно пришло.",
        "The invitation was sent to another address. Sign in with the account it was sent to.",
    ),
    IdentityErrorCode.access_request_decided: (
        "Запрос уже рассмотрен.",
        "The request has already been decided.",
    ),
    IdentityErrorCode.confirm_name_mismatch: (
        "Имя проекта введено неверно.",
        "The project name does not match.",
    ),
    IdentityErrorCode.transfer_expired: (
        "Срок передачи истёк.",
        "The transfer has expired.",
    ),
    IdentityErrorCode.transfer_outdated: (
        "Владелец проекта уже сменился: передача больше не действует.",
        "The project owner has changed: this transfer no longer applies.",
    ),
    IdentityErrorCode.git_scope_missing: (
        "У токена нет доступа к git: нужен scope git:read или git:write.",
        "The token has no git access: git:read or git:write is required.",
    ),
    IdentityErrorCode.git_busy: (
        "Слишком много одновременных запросов git. Повторите позже.",
        "Too many concurrent git requests. Try again later.",
    ),
    IdentityErrorCode.git_project_busy: (
        "Проект сейчас занят (обновление шаблона или синхронизация). Повторите позже.",
        "The project is busy (template update or sync). Try again later.",
    ),
    IdentityErrorCode.device_scope_invalid: (
        "Устройство может просить только git:read и git:write.",
        "A device may only ask for git:read and git:write.",
    ),
    IdentityErrorCode.device_code_invalid: ("Код не найден.", "Code not found."),
    IdentityErrorCode.device_code_expired: ("Срок кода истёк.", "The code has expired."),
    IdentityErrorCode.device_code_used: ("Код уже подтверждён или отклонён.", "The code was already decided."),
    IdentityErrorCode.git_server_url_invalid: (
        "Адрес сервера должен начинаться с https:// (http только для localhost).",
        "The server address must start with https:// (http only for localhost).",
    ),
    IdentityErrorCode.git_server_not_studio: (
        "По этому адресу нет сервера HSE Doc Studio.",
        "There is no HSE Doc Studio server at this address.",
    ),
    IdentityErrorCode.git_server_unreachable: (
        "Сервер не отвечает. Проверьте адрес и сеть.",
        "The server isn't responding. Check the address and the network.",
    ),
}


def message_for(code: IdentityErrorCode) -> str:
    ru, en = MESSAGES[code]
    return localized_error(ru, en)


class IdentityError(Exception):
    """Ошибка identity с кодом из закрытого списка; `detail` уже локализован."""

    def __init__(
        self,
        code: IdentityErrorCode,
        detail: str = "",
        *,
        retry_after_s: int | None = None,
        status: int | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        detail = detail or message_for(code)
        super().__init__(detail)
        self.code = code
        self.detail = detail
        # Для rate_limited: через сколько секунд повторить (заголовок Retry-After).
        self.retry_after_s = retry_after_s
        # Статус вместо табличного: один код в разных местах значит разное (`invitation_required` у
        # регистрации 403, у добавления в проект 409).
        self.status = status
        # Дополнительные поля тела ответа (например, id ожидающего приглашения).
        self.extra = extra or {}
