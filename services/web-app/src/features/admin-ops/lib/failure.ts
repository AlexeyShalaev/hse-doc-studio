// Отказы операционных экранов: код каталога ошибок или "network" и "unknown".
export const KNOWN_FAILURES = [
  "not_found",
  "forbidden",
  "setting_locked",
  "rate_limited",
  "csrf_failed",
  "input_invalid",
  "network",
] as const;

export const failureKey = (code: string): string =>
  (KNOWN_FAILURES as readonly string[]).includes(code)
    ? `adminOps:failure.${code}`
    : "adminOps:failure.unknown";

export type Failure = { code: string };
