// Отказы экранов организаций: код каталога ошибок или "network" и "unknown".
export const KNOWN_FAILURES = [
  "last_owner",
  "already_member",
  "org_not_empty",
  "slug_taken",
  "slug_reserved",
  "slug_invalid",
  "not_found",
  "member_not_found",
  "forbidden",
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
