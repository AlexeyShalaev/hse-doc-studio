// Коды отказа регистрации со своим текстом. Сеть, 5xx и неизвестный код идут
// общей строкой. Почта «уже занята» среди них нет намеренно: ответ нейтральный.
export const REGISTER_ERROR_CODES = [
  "registration_closed",
  "domain_not_allowed",
  "invitation_required",
  "invitation_invalid",
  "password_policy",
  "rate_limited",
  "csrf_failed",
] as const;

export type RegisterErrorCode = (typeof REGISTER_ERROR_CODES)[number];

export const isKnownRegisterCode = (code: string): code is RegisterErrorCode =>
  (REGISTER_ERROR_CODES as readonly string[]).includes(code);

export const registerErrorKey = (code: string): string =>
  isKnownRegisterCode(code) || code === "network"
    ? `register.errors.${code}`
    : "register.errors.unknown";

/** Эти отказы относятся к полю, остальные выводятся рамкой над формой. */
export const fieldOfFailure = (code: string): "email" | "password" | null =>
  code === "domain_not_allowed"
    ? "email"
    : code === "password_policy"
      ? "password"
      : null;
