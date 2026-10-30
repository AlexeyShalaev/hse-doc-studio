import { failureCode } from "@shared/api";

/** Состояние загрузки вида: forbidden отдельно, у него своё объяснение. */
export type ViewStatus = "loading" | "error" | "forbidden" | "ready";

const DENIED = new Set(["forbidden", "not_found"]);

/**
 * Уже полученные данные важнее ошибки: неудачный фоновый опрос
 * не заменяет таблицу ошибкой, она остаётся с прежними данными.
 */
export const statusOf = (q: {
  data: unknown;
  isError: boolean;
  error?: unknown;
}): ViewStatus =>
  q.data !== undefined
    ? "ready"
    : q.isError
      ? DENIED.has(failureCode(q.error))
        ? "forbidden"
        : "error"
      : "loading";
