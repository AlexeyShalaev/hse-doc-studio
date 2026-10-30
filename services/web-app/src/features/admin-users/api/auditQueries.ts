import { useQuery } from "@tanstack/react-query";
import { auditApi } from "./auditApi";

// Ключи журнала начинаются с ["admin", "audit"]: любое действие над людьми
// сбрасывает их разом (adminUsersQueries.useChanged).
export const auditKeys = {
  all: ["admin", "audit"] as const,
  recent: (limit: number) => [...auditKeys.all, "recent", limit] as const,
};

/** Последние записи журнала для сводки: одна короткая страница, без справочника людей. */
export const useRecentAudit = (limit: number) =>
  useQuery({
    queryKey: auditKeys.recent(limit),
    queryFn: ({ signal }) => auditApi.page({ limit }, signal),
    staleTime: 0,
  });
