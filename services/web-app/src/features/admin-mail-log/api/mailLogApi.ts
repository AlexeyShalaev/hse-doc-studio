import { adminClient, parseResp } from "@shared/api";
import type { ListRequestParams } from "@shared/lib";
import {
  MailLogDetailSchema,
  MailLogPageSchema,
  MailLogSummarySchema,
  type MailLogDetail,
  type MailLogPage,
  type MailLogSummary,
} from "./schemas";

// Журнал писем (docs/design/mail-log.md, 6.1): /api/admin/mail-log. Только админ установки по
// сессии; не админу сервер отвечает 404, анониму 401. Ошибки показывает сам экран: без тоста.

const quiet = { silentError: true } as const;
const opts = (signal: AbortSignal | undefined) =>
  signal ? { ...quiet, signal } : quiet;

export const mailLogApi = {
  /**
   * Страница журнала, новые сверху; дальше по `next_cursor`. Параметры и их имена в адресе
   * страницы: MAIL_LOG_LIST (mailLogQueries.ts).
   */
  page: (
    params: ListRequestParams & { cursor?: string },
    signal?: AbortSignal,
  ): Promise<MailLogPage> =>
    adminClient
      .get("/mail-log", { ...opts(signal), params })
      .then(parseResp(MailLogPageSchema)),
  /** Карточка с превью; 404 `not_found`, если строка удалена по сроку. */
  entry: (id: number, signal?: AbortSignal): Promise<MailLogDetail> =>
    adminClient
      .get(`/mail-log/${String(id)}`, opts(signal))
      .then(parseResp(MailLogDetailSchema)),
  /** Итоги за сутки, последний сбой и настроена ли почта. */
  summary: (signal?: AbortSignal): Promise<MailLogSummary> =>
    adminClient
      .get("/mail-log/summary", opts(signal))
      .then(parseResp(MailLogSummarySchema)),
};
