import { ApiError } from "@shared/api/client";
import type { ClientProblem } from "./uploadPlan";

/** Почему файл не загрузился: код для текста и подробности. */
export type FailureReason = {
  code:
    | ClientProblem
    | "quota_server"
    | "read_only"
    | "forbidden"
    | "network"
    | "canceled"
    | "stopped"
    | "server";
  /** Предел в байтах для `too_large`, свободное место для `quota`. */
  bytes?: number;
  /** Текст сервера для `server`: он уже на языке интерфейса. */
  detail?: string;
};

export type UploadOutcome =
  | { path: string; status: "uploaded"; replaced: boolean }
  | { path: string; status: "skipped" }
  | { path: string; status: "failed"; reason: FailureReason };

// После таких отказов следующие файлы тоже не пройдут: загрузку лучше остановить.
const FATAL_CODES = new Set<FailureReason["code"]>([
  "quota_server",
  "read_only",
  "network",
]);
const FATAL_SERVER_CODES = new Set([
  "storage_critical",
  "owner_storage_exceeded",
  "csrf_failed",
]);

export const isFatal = (reason: FailureReason, serverCode?: string): boolean =>
  FATAL_CODES.has(reason.code) ||
  (serverCode !== undefined && FATAL_SERVER_CODES.has(serverCode));

const numberOf = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;

/** Отказ сервера на один файл в причину для итога загрузки. */
export const serverFailure = (error: unknown): FailureReason => {
  if (!(error instanceof ApiError)) return { code: "network" };
  if (error.status === 0) return { code: "network" };
  if (error.code === "file_too_large") {
    const limit = numberOf(error.data?.limit);
    return limit === undefined
      ? { code: "too_large" }
      : { code: "too_large", bytes: limit };
  }
  if (error.code === "project_quota_exceeded") return { code: "quota_server" };
  if (error.code === "path_conflict") return { code: "folder_conflict" };
  if (error.status === 423) return { code: "read_only" };
  if (
    error.status === 403 &&
    (error.code === "forbidden" || error.code === "forbidden_role")
  ) {
    return { code: "forbidden" };
  }
  return { code: "server", detail: error.detail };
};
