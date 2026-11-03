// Коды отказа регистрации со своим текстом. Сеть, 5xx и неизвестный код идут
// общей строкой. Почта «уже занята» приходит только в регистрации с passkey по приглашению на адрес.
export const REGISTER_ERROR_CODES = [
  "registration_closed",
  "domain_not_allowed",
  "invitation_required",
  "invitation_invalid",
  "password_policy",
  "rate_limited",
  "csrf_failed",
  // Регистрация с passkey: приглашение на этот адрес уже использовано аккаунтом (ссылку получил его владелец,
  // поэтому сказать «войдите» можно), passkey выключен или не прошёл проверку.
  "email_taken",
  "passkeys_disabled",
  "passkey_invalid",
] as const;

// Не код сервера: браузер не создал ключ (сбой церемонии, кроме отмены).
export const PASSKEY_CEREMONY_FAILED = "passkey_failed";

export type RegisterErrorCode = (typeof REGISTER_ERROR_CODES)[number];

export const isKnownRegisterCode = (code: string): code is RegisterErrorCode =>
  (REGISTER_ERROR_CODES as readonly string[]).includes(code);

export const registerErrorKey = (code: string): string =>
  isKnownRegisterCode(code) ||
  code === "network" ||
  code === PASSKEY_CEREMONY_FAILED
    ? `register.errors.${code}`
    : "register.errors.unknown";

/** Эти отказы относятся к полю, остальные выводятся рамкой над формой. */
export const fieldOfFailure = (code: string): "email" | "password" | null =>
  code === "domain_not_allowed"
    ? "email"
    : code === "password_policy"
      ? "password"
      : null;
