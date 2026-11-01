// Отказы экранов людей: код каталога ошибок или "network" и "unknown".
export const KNOWN_FAILURES = [
  "last_admin",
  "user_has_projects",
  "user_not_disabled",
  "not_found",
  "forbidden",
  "invitation_invalid",
  "rate_limited",
  "csrf_failed",
  "input_invalid",
  "network",
] as const;

export const failureKey = (code: string): string =>
  (KNOWN_FAILURES as readonly string[]).includes(code)
    ? `failure.${code}`
    : "failure.unknown";

export type Failure = { code: string };
