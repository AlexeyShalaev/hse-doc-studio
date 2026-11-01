// Коды отказов шагов мастера со своим текстом. Сеть, 5xx и неизвестный код
// идут общей строкой.
export const SETUP_ERROR_CODES = [
  "setup_token_invalid",
  "setup_already_done",
  "password_policy",
  "rate_limited",
  "csrf_failed",
  "forbidden",
  "auth_required",
  "setting_locked",
  "network",
] as const;

export type SetupErrorCode = (typeof SETUP_ERROR_CODES)[number];

export const isKnownSetupCode = (code: string): code is SetupErrorCode =>
  (SETUP_ERROR_CODES as readonly string[]).includes(code);

export const setupErrorKey = (code: string): string =>
  isKnownSetupCode(code) ? `setup.errors.${code}` : "setup.errors.unknown";

/** Отказы, которые относятся к полю формы администратора, а не ко всей форме. */
export const fieldOfSetupFailure = (
  code: string,
): "setup_token" | "password" | null =>
  code === "setup_token_invalid"
    ? "setup_token"
    : code === "password_policy"
      ? "password"
      : null;
