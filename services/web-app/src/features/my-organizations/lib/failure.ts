// Отказы раздела: код каталога ошибок или "network" и "unknown".
export const KNOWN_FAILURES = [
  "last_owner",
  "not_found",
  "forbidden",
  "rate_limited",
  "csrf_failed",
  "network",
] as const;

export const failureKey = (code: string): string =>
  (KNOWN_FAILURES as readonly string[]).includes(code)
    ? `failure.${code}`
    : "failure.unknown";

export type Failure = { code: string };
