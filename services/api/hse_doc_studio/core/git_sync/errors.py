from enum import StrEnum


class GitErrorCode(StrEnum):
    """Закрытый список кодов ошибок Git-синхронизации: тело ответа {detail, code}.

    Источник правды — contracts/git-sync/error_codes.json; тест контракта сверяет список
    с этим перечислением, TS-константой и ключами errors:code.* в ru и en.
    """

    url_invalid = "url_invalid"
    url_scheme_forbidden = "url_scheme_forbidden"
    provider_unknown = "provider_unknown"
    host_settings_invalid = "host_settings_invalid"
    credential_invalid = "credential_invalid"
    credential_in_use = "credential_in_use"
    credential_host_mismatch = "credential_host_mismatch"
    credentials_missing = "credentials_missing"
    secrets_unavailable = "secrets_unavailable"
    store_untrusted = "store_untrusted"
    profile_required = "profile_required"
    auth_failed = "auth_failed"
    forbidden_write = "forbidden_write"
    sso_required = "sso_required"
    token_expired = "token_expired"  # noqa: S105 — код ошибки, не пароль
    not_found_or_no_access = "not_found_or_no_access"
    rate_limited = "rate_limited"
    host_key_unknown = "host_key_unknown"
    host_key_changed = "host_key_changed"
    offline = "offline"
    tls_error = "tls_error"
    tls_untrusted_ca = "tls_untrusted_ca"
    tls_pin_mismatch = "tls_pin_mismatch"
    timeout = "timeout"
    ssh_unavailable = "ssh_unavailable"
    git_unavailable = "git_unavailable"
    git_disabled = "git_disabled"
    branch_missing = "branch_missing"
    remote_exists = "remote_exists"
    not_a_studio_project = "not_a_studio_project"
    unrelated_histories = "unrelated_histories"
    project_exists = "project_exists"
    folder_not_empty = "folder_not_empty"
    sync_busy = "sync_busy"
    sync_busy_build = "sync_busy_build"
    off_branch = "off_branch"
    sync_incomplete = "sync_incomplete"
    plan_outdated = "plan_outdated"
    no_conflicts = "no_conflicts"
    unresolved_conflicts = "unresolved_conflicts"
    invalid_resolution = "invalid_resolution"
    unresolved_markers = "unresolved_markers"
    remote_moved = "remote_moved"
    protected_branch = "protected_branch"
    # Сервер Студии отклонил push проверкой pre-receive (область автора, служебные пути, размер, схема).
    push_rejected = "push_rejected"
    large_file = "large_file"
    workflow_scope_missing = "workflow_scope_missing"
    email_privacy = "email_privacy"
    remote_schema_newer = "remote_schema_newer"
    bundle_invalid = "bundle_invalid"
    bundle_password_required = "bundle_password_required"  # noqa: S105 — код ошибки, не пароль
    bundle_password_wrong = "bundle_password_wrong"  # noqa: S105 — код ошибки, не пароль
    bundle_prerequisites_missing = "bundle_prerequisites_missing"
    operation_not_cancellable = "operation_not_cancellable"
    egress_blocked = "egress_blocked"
    git_error = "git_error"


class GitSyncError(Exception):
    """Ошибка Git-синхронизации с кодом из закрытого списка.

    `detail` уже локализован и очищен от секретов: он уходит клиенту как есть.
    `ctx` — дополнительные поля тела ответа (operation_id, required_studio, expected, actual и т. п.).
    """

    def __init__(self, code: GitErrorCode, detail: str = "", **ctx: object) -> None:
        super().__init__(detail or code.value)
        self.code = code
        self.detail = detail or code.value
        self.ctx = ctx


class GitUrlError(GitSyncError):
    """Адрес репозитория не принят: url_invalid или url_scheme_forbidden."""
