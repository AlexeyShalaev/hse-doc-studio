import { failureCode } from "@shared/api";

/** Состояние загрузки вида: forbidden отдельно, у него своё объяснение. */
export type ViewStatus = "loading" | "error" | "forbidden" | "ready";

const DENIED = new Set(["forbidden", "not_found"]);

export const statusOf = (q: {
  isError: boolean;
  isPending: boolean;
  error?: unknown;
}): ViewStatus =>
  q.isError
    ? DENIED.has(failureCode(q.error))
      ? "forbidden"
      : "error"
    : q.isPending
      ? "loading"
      : "ready";
