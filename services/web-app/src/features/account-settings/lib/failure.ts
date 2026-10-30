// Отказы форм аккаунта: код каталога ошибок или "network" и "unknown".
export const KNOWN_FAILURES = [
  "invalid_credentials",
  "password_policy",
  "rate_limited",
  "csrf_failed",
  "email_taken",
  "forbidden",
  "last_login_method",
  "network",
] as const;

export const failureKey = (code: string): string =>
  (KNOWN_FAILURES as readonly string[]).includes(code)
    ? `failure.${code}`
    : "failure.unknown";

export type Failure = { code: string };
