// Закрытый список кодов ошибок Git-синхронизации. Источник правды:
// contracts/git-sync/error_codes.json; контрактный тест сверяет этот список с JSON,
// с перечислением GitErrorCode на бэкенде и с ключами errors:code.* в ru и en.
export const GIT_ERROR_CODES = [
  "url_invalid",
  "url_scheme_forbidden",
  "provider_unknown",
  "host_settings_invalid",
  "credential_invalid",
  "credential_in_use",
  "credential_host_mismatch",
  "credentials_missing",
  "secrets_unavailable",
  "store_untrusted",
  "profile_required",
  "auth_failed",
  "forbidden_write",
  "sso_required",
  "token_expired",
  "not_found_or_no_access",
  "rate_limited",
  "host_key_unknown",
  "host_key_changed",
  "offline",
  "tls_error",
  "tls_untrusted_ca",
  "tls_pin_mismatch",
  "timeout",
  "ssh_unavailable",
  "git_unavailable",
  "git_disabled",
  "branch_missing",
  "remote_exists",
  "not_a_studio_project",
  "unrelated_histories",
  "project_exists",
  "folder_not_empty",
  "sync_busy",
  "sync_busy_build",
  "off_branch",
  "sync_incomplete",
  "plan_outdated",
  "no_conflicts",
  "unresolved_conflicts",
  "invalid_resolution",
  "unresolved_markers",
  "remote_moved",
  "protected_branch",
  "large_file",
  "workflow_scope_missing",
  "email_privacy",
  "remote_schema_newer",
  "bundle_invalid",
  "bundle_password_required",
  "bundle_password_wrong",
  "bundle_prerequisites_missing",
  "operation_not_cancellable",
  "git_error",
] as const;

export type GitErrorCode = (typeof GIT_ERROR_CODES)[number];

// Незнакомый код от более новой Студии не ломает разбор: проверяем перед выбором текста.
export const isGitErrorCode = (value: unknown): value is GitErrorCode =>
  typeof value === "string" &&
  (GIT_ERROR_CODES as readonly string[]).includes(value);

// Ключ перевода сообщения по коду; для незнакомого кода возвращает null.
export const gitErrorI18nKey = (code: unknown): string | null =>
  isGitErrorCode(code) ? `errors:code.${code}` : null;
