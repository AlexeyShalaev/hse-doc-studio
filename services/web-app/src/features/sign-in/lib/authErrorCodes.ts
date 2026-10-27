// Причины, по которым внешний вход (OIDC) вернул человека на /auth/error?code=.
export const AUTH_ERROR_CODES = [
  "oidc_denied",
  "oidc_failed",
  "sso_login_required",
  "account_disabled",
  "pending_approval",
  "email_not_verified",
  "domain_not_allowed",
  "registration_closed",
  "invitation_required",
  "rate_limited",
] as const;

export type AuthErrorCode = (typeof AUTH_ERROR_CODES)[number];

export const normalizeAuthErrorCode = (
  raw: string | null,
): AuthErrorCode | "unknown" =>
  (AUTH_ERROR_CODES as readonly string[]).includes(raw ?? "")
    ? (raw as AuthErrorCode)
    : "unknown";

export const authErrorTone = (
  code: AuthErrorCode | "unknown",
): "warn" | "err" =>
  code === "pending_approval" ||
  code === "email_not_verified" ||
  code === "oidc_denied"
    ? "warn"
    : "err";
