import { ApiError } from "@shared/api";

export type UpdateFailure = { code: string; field: string | null };

const KNOWN = [
  "invalid_input",
  "not_found",
  "executor_unavailable",
  "updater_offline",
  "already_running",
  "nothing_to_update",
  "unknown_version",
  "no_previous_version",
  "not_cancellable",
  "risk_not_confirmed",
  "rollback_unsafe",
  "forbidden",
  "rate_limited",
  "csrf_failed",
  "network",
] as const;

export const failureOf = (error: unknown): UpdateFailure => {
  if (error instanceof ApiError) {
    const field = error.data?.field;
    return {
      code: error.status === 0 ? "network" : error.code,
      field: typeof field === "string" ? field : null,
    };
  }
  return { code: "unknown", field: null };
};

export const failureKey = (code: string): string =>
  (KNOWN as readonly string[]).includes(code)
    ? `failure.${code}`
    : "failure.unknown";
