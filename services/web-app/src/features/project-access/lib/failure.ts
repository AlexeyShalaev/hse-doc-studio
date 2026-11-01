export const KNOWN_FAILURES = [
  "last_owner",
  "member_not_found",
  "not_found",
  "forbidden",
  "rate_limited",
  "csrf_failed",
  "network",
] as const;

// Бэкенд отвечает на неизвестного человека кодом user_not_found: для панели это тот же отказ.
export const failureKey = (code: string): string => {
  const known = code === "user_not_found" ? "member_not_found" : code;
  return (KNOWN_FAILURES as readonly string[]).includes(known)
    ? `panel.failure.${known}`
    : "panel.failure.unknown";
};

export type Failure = { code: string };
