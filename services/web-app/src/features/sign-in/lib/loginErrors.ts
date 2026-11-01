// Коды отказа входа, у которых есть собственный текст на экране. Всё
// остальное (сеть, 5xx, неизвестный код) показывается общей строкой.
export const LOGIN_ERROR_CODES = [
  "invalid_credentials",
  "email_not_verified",
  "pending_approval",
  "account_disabled",
  "sso_login_required",
  "rate_limited",
  "csrf_failed",
] as const;

export type LoginErrorCode = (typeof LOGIN_ERROR_CODES)[number];

export type LoginFailure = {
  /** Код из contracts/server/error_codes.json или "network" / "unknown". */
  code: string;
  /** Сколько секунд ждать (rate_limited). */
  retryAfter?: number;
};

export const DEFAULT_RETRY_AFTER = 30;

export const isKnownLoginCode = (code: string): code is LoginErrorCode =>
  (LOGIN_ERROR_CODES as readonly string[]).includes(code);

/** Ключ текста ошибки в пространстве auth. */
export const loginErrorKey = (code: string): string =>
  isKnownLoginCode(code)
    ? `login.errors.${code}`
    : code === "network"
      ? "login.errors.network"
      : "login.errors.unknown";

/** Тон рамки: ожидание и ожидаемые отказы мягче, остальное красным. */
export const loginErrorTone = (code: string): "warn" | "err" =>
  code === "rate_limited" ||
  code === "email_not_verified" ||
  code === "pending_approval"
    ? "warn"
    : "err";
