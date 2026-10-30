export const KNOWN_FAILURES = [
  "last_owner",
  "member_not_found",
  "not_found",
  "forbidden",
  "rate_limited",
  "csrf_failed",
  "network",
] as const;

export const failureKey = (code: string): string =>
  (KNOWN_FAILURES as readonly string[]).includes(code)
    ? `panel.failure.${code}`
    : "panel.failure.unknown";

export type Failure = { code: string };
