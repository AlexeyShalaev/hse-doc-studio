import { ApiError } from "@shared/api";

export type BackupFailure = { code: string; field: string | null };

const KNOWN = [
  "backup_invalid_input",
  "backup_not_found",
  "backup_conflict",
  "backup_already_running",
  "backup_no_destination",
  "backup_secrets_unavailable",
  "backup_unsupported",
  "backup_unsafe_target",
  "backup_destination_unreachable",
  "backup_integrity",
  "backup_restore_busy",
  "backup_restore_unconfirmed",
  "backup_restore_failed",
  "backup_restore_interrupted",
  "maintenance",
  "not_found",
  "forbidden",
  "rate_limited",
  "csrf_failed",
  "input_invalid",
  "network",
] as const;

export const failureOf = (error: unknown): BackupFailure => {
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
