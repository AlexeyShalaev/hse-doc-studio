import { adminClient, parseResp } from "@shared/api";
import type { ListRequestParams } from "@shared/lib";
import { AdminAuditPageSchema, type AdminAuditPage } from "@entities/session";

// Журнал аудита установки: курсор, новые первыми. Поиск, разделы, человек и
// период считает сервер; имя действовавшего и подпись цели приходят в строке.

const quiet = { silentError: true } as const;

/** Разделы журнала: приставка действия до точки (`auth.login` в разделе auth). */
export const AUDIT_CATEGORIES = [
  "auth",
  "admin",
  "invite",
  "org",
  "group",
  "settings",
  "runner",
  "project",
] as const;

export type AuditCategoryName = (typeof AUDIT_CATEGORIES)[number];

export const auditApi = {
  page: (
    params: ListRequestParams & { cursor?: string },
    signal: AbortSignal,
  ): Promise<AdminAuditPage> =>
    adminClient
      .get("/audit", { ...quiet, signal, params })
      .then(parseResp(AdminAuditPageSchema)),
};
