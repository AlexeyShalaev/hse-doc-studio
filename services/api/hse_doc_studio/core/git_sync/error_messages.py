"""Тексты ошибок удалённого git: клиент показывает свой текст по коду, этот остаётся запасным в `detail`."""

from __future__ import annotations

from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.i18n import localized_error

_MESSAGES: dict[GitErrorCode, tuple[str, str]] = {
    GitErrorCode.credentials_missing: (
        "Для репозитория нужен доступ: добавьте токен или ключ",
        "The repository needs access: add a token or a key",
    ),
    GitErrorCode.auth_failed: (
        "Сервер не принял доступ. Проверьте токен или ключ",
        "The server rejected the access. Check the token or the key",
    ),
    GitErrorCode.forbidden_write: (
        "У этого доступа нет права записи в репозиторий",
        "This access cannot write to the repository",
    ),
    GitErrorCode.sso_required: (
        "Токен нужно разрешить для организации (SSO)",
        "The token must be authorized for the organization (SSO)",
    ),
    GitErrorCode.not_found_or_no_access: (
        "Репозиторий не найден или нет доступа к нему",
        "The repository was not found or you have no access to it",
    ),
    GitErrorCode.rate_limited: (
        "Сервер просит подождать: слишком много запросов",
        "The server asks to wait: too many requests",
    ),
    GitErrorCode.host_key_unknown: (
        "Ключ сервера ещё не подтверждён",
        "The server key has not been confirmed yet",
    ),
    GitErrorCode.host_key_changed: (
        "Ключ сервера изменился с прошлого подключения",
        "The server key has changed since the last connection",
    ),
    GitErrorCode.offline: (
        "Нет связи с сервером. Проверьте сеть и адрес",
        "The server is unreachable. Check the network and the address",
    ),
    GitErrorCode.tls_error: (
        "Не удалось проверить сертификат сервера",
        "The server certificate could not be verified",
    ),
    GitErrorCode.tls_untrusted_ca: (
        "Сертификат сервера выдан неизвестным центром. Добавьте его сертификат или подтвердите отпечаток",
        "The server certificate was issued by an unknown authority. Add its certificate or confirm the fingerprint",
    ),
    GitErrorCode.tls_pin_mismatch: (
        "Сертификат сервера отличается от подтверждённого раньше",
        "The server certificate differs from the one confirmed earlier",
    ),
    GitErrorCode.token_expired: (
        "Срок действия токена истёк. Выпустите новый",
        "The token has expired. Issue a new one",
    ),
    GitErrorCode.token_insufficient_scope: (
        "Токену не хватает прав для чтения и записи репозитория",
        "The token lacks the permissions to read and write the repository",
    ),
    GitErrorCode.provider_unknown: (
        "Неизвестный тип сервера. Выберите GitHub, GitLab, Gitea, Bitbucket или другое",
        "Unknown server type. Choose GitHub, GitLab, Gitea, Bitbucket or other",
    ),
    GitErrorCode.host_settings_invalid: (
        "Настройки сервера заполнены неверно: проверьте сертификат и отпечаток",
        "The server settings are not valid: check the certificate and the fingerprint",
    ),
    GitErrorCode.timeout: (
        "Сервер не ответил вовремя. Попробуйте ещё раз",
        "The server did not answer in time. Try again",
    ),
    GitErrorCode.ssh_unavailable: (
        "В системе нет ssh. Установите клиент OpenSSH или используйте https",
        "ssh is not available. Install the OpenSSH client or use https",
    ),
    GitErrorCode.git_unavailable: (
        "Git не найден или слишком старый. Нужен Git не ниже 2.31",
        "Git was not found or is too old. Git 2.31 or newer is required",
    ),
    GitErrorCode.profile_required: (
        "Сначала укажите имя и почту автора: они попадут в историю проекта",
        "Set your author name and e-mail first: they go into the project history",
    ),
    GitErrorCode.sync_busy: (
        "С этим проектом уже идёт синхронизация. Дождитесь её окончания",
        "This project is already being synchronized. Wait for it to finish",
    ),
    GitErrorCode.remote_exists: (
        "К проекту уже подключён удалённый репозиторий. Сначала отключите его",
        "A remote repository is already connected to this project. Disconnect it first",
    ),
    GitErrorCode.not_a_studio_project: (
        "В репозитории нет проекта Студии: подключайте репозиторий, созданный из проекта",
        "The repository has no Studio project: connect a repository created from a project",
    ),
    GitErrorCode.unrelated_histories: (
        "В репозитории лежит другой проект или у него нет общей истории с этим",
        "The repository holds another project or has no history in common with this one",
    ),
    GitErrorCode.off_branch: (
        "Проект стоит не на той ветке, которая синхронизируется",
        "The project is not on the branch that is being synchronized",
    ),
    GitErrorCode.operation_not_cancellable: (
        "Эту операцию уже нельзя отменить",
        "This operation can no longer be cancelled",
    ),
    GitErrorCode.remote_schema_newer: (
        "Проект в репозитории записан более новой Студией. Обновите Студию",
        "The project in the repository was saved by a newer Studio. Update the Studio",
    ),
    GitErrorCode.branch_missing: (
        "В репозитории нет такой ветки",
        "The repository has no such branch",
    ),
    GitErrorCode.remote_moved: (
        "В репозиторий успели записать новые изменения",
        "New changes were pushed to the repository in the meantime",
    ),
    GitErrorCode.protected_branch: (
        "Ветка защищена: прямая запись в неё запрещена",
        "The branch is protected: direct pushes are not allowed",
    ),
    GitErrorCode.large_file: (
        "В проекте есть файл, который сервер не принимает по размеру",
        "The project has a file that the server rejects because of its size",
    ),
    GitErrorCode.workflow_scope_missing: (
        "Токену не хватает права на изменение рабочих процессов (workflow)",
        "The token lacks the permission to change workflows",
    ),
    GitErrorCode.email_privacy: (
        "Сервер не принял адрес почты автора: он скрыт настройками приватности",
        "The server rejected the author e-mail: it is hidden by privacy settings",
    ),
}


def git_error(code: GitErrorCode, *, tail: str | None = None, **ctx: object) -> GitSyncError:
    """Ошибка с понятным текстом. Для git_error в текст идёт очищенный хвост вывода git, он и есть объяснение."""
    if code is GitErrorCode.git_error:
        text = tail or localized_error("Git завершился с ошибкой", "Git finished with an error")
    else:
        ru, en = _MESSAGES.get(code, (code.value, code.value))
        text = localized_error(ru, en)
    return GitSyncError(code, text, **ctx)
