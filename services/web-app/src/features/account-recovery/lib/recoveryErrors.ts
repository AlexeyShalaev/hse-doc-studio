// Коды отказа у экранов «забыл пароль», «новый пароль» и подтверждения почты.
// Остальное (сеть, 5xx, неизвестный код) идёт общей строкой.
export const RECOVERY_ERROR_CODES = [
  "token_invalid",
  "password_policy",
  "rate_limited",
  "csrf_failed",
] as const;

export type RecoveryErrorCode = (typeof RECOVERY_ERROR_CODES)[number];

export const recoveryErrorKey = (code: string): string =>
  (RECOVERY_ERROR_CODES as readonly string[]).includes(code) ||
  code === "network"
    ? `recovery.errors.${code}`
    : "recovery.errors.unknown";

export type RecoveryFailure = { code: string };
