// Куда вернуть человека, когда клонирование не удалось: к тому, что нужно
// исправить. Чистые функции, без интерфейса.

export type CloneFailureTarget = "profile" | "source" | "folder" | "general";

const BUNDLE_CODES = new Set([
  "bundle_invalid",
  "bundle_password_required",
  "bundle_password_wrong",
  "bundle_prerequisites_missing",
]);

const FOLDER_CODES = new Set(["folder_not_empty", "project_exists"]);

const SOURCE_CODES = new Set([
  "url_invalid",
  "url_scheme_forbidden",
  "credential_invalid",
  "credential_host_mismatch",
  "credentials_missing",
  "secrets_unavailable",
  "auth_failed",
  "forbidden_write",
  "sso_required",
  "not_found_or_no_access",
  "rate_limited",
  "host_key_unknown",
  "host_key_changed",
  "offline",
  "tls_error",
  "timeout",
  "ssh_unavailable",
  "branch_missing",
  "not_a_studio_project",
  "remote_schema_newer",
  "store_untrusted",
]);

export const cloneFailureTarget = (code: string): CloneFailureTarget => {
  if (code === "profile_required") return "profile";
  if (FOLDER_CODES.has(code)) return "folder";
  if (BUNDLE_CODES.has(code) || SOURCE_CODES.has(code)) return "source";
  return "general";
};

/** Ошибки пароля и файла bundle показываются у самих полей. */
export const isBundleCode = (code: string): boolean => BUNDLE_CODES.has(code);
