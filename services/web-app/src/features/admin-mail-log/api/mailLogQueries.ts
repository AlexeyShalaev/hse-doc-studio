import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import {
  useCursorList,
  type ListQueryState,
  type ListRequestParams,
  type ListStateOptions,
} from "@shared/lib";
import { mailLogApi } from "./mailLogApi";
import {
  MAIL_STATUSES,
  type MailLogEntry,
  type MailLogResendBatchRequest,
} from "./schemas";

// Запросы журнала писем (docs/design/mail-log.md, 4.1 и 6). Ключи начинаются с
// ["admin", "mail-log"]: тестовое письмо и смена настроек почты сбрасывают их разом.

export const mailLogKeys = {
  all: ["admin", "mail-log"] as const,
  list: ["admin", "mail-log", "list"] as const,
  entry: (id: number) => ["admin", "mail-log", "entry", id] as const,
  summary: ["admin", "mail-log", "summary"] as const,
};

/** Сводка за сутки перечитывается раз в минуту: счётчик в меню и полоса раздела (L14). */
export const MAIL_LOG_SUMMARY_POLL_MS = 60_000;

/**
 * Состояние журнала в адресе страницы (6.1): поиск `q`, виды, итоги, причина, получатель (по
 * человеку или точному адресу), проект и период. Сортировки нет: новые сверху (L13). Вид письма
 * не ограничен списком: в журнале бывают виды, которых в этой версии уже нет.
 */
export const MAIL_LOG_LIST = {
  mode: "cursor",
  filters: {
    template: { multi: true },
    status: { multi: true, values: MAIL_STATUSES },
    reason: {},
    // Ждут автоповтора (14, V13): ставит полоса за сутки, в панели виден чипом.
    retrying: { values: ["true", "false"] },
    recipient_id: {},
    recipient: {},
    project_id: {},
    from: { date: "from" },
    to: { date: "to" },
  },
} as const satisfies ListStateOptions<string, never>;

export type MailLogFilterName = keyof typeof MAIL_LOG_LIST.filters;
export type MailLogListState = ListQueryState<MailLogFilterName, never>;

const idOf = (row: MailLogEntry): string => String(row.id);

/** Страницы журнала по курсору с «Показать ещё»; params берутся из состояния в адресе. */
export const useMailLog = (
  state: Pick<ListQueryState, "params">,
  options: { enabled?: boolean; pollMs?: number } = {},
) =>
  useCursorList({
    state,
    queryKey: mailLogKeys.list,
    fetchPage: mailLogApi.page,
    getId: idOf,
    ...(options.enabled === undefined ? {} : { enabled: options.enabled }),
    ...(options.pollMs === undefined ? {} : { pollMs: options.pollMs }),
  });

/** Строки нет (удалена по сроку) или раздел недоступен: повтор не поможет. */
export const isMailLogNotFound = (error: unknown): boolean =>
  error instanceof ApiError && error.status === 404;

/** Карточка письма по `?mail=<id>`; null закрывает карточку и не ходит на сервер. */
export const useMailLogEntry = (id: number | null) =>
  useQuery({
    queryKey: mailLogKeys.entry(id ?? 0),
    queryFn: ({ signal }) => mailLogApi.entry(id ?? 0, signal),
    enabled: id !== null,
    staleTime: 0,
    retry: (count, error) => !isMailLogNotFound(error) && count < 1,
  });

/** Итоги за сутки: полоса раздела, плашка «Почта не настроена» и счётчик меню. */
export const useMailLogSummary = (options: { enabled?: boolean } = {}) =>
  useQuery({
    queryKey: mailLogKeys.summary,
    queryFn: ({ signal }) => mailLogApi.summary(signal),
    enabled: options.enabled ?? true,
    staleTime: 0,
    refetchInterval: MAIL_LOG_SUMMARY_POLL_MS,
  });

/** Повтор меняет журнал и сводку: новая строка, у исходной «Отправлено ещё раз». */
const useInvalidateMailLog = () => {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: mailLogKeys.all });
};

/** «Отправить ещё раз» на карточке письма. */
export const useResendMail = () => {
  const invalidate = useInvalidateMailLog();
  return useMutation({
    mutationFn: (id: number) => mailLogApi.resend(id),
    onSettled: invalidate,
  });
};

/** Фильтры списка (параметры адреса) как тело «Отправить неушедшие»: без итога и курсора. */
export const resendBatchBodyOf = (
  params: ListRequestParams,
  dryRun: boolean,
): MailLogResendBatchRequest => {
  const one = (key: string): string | null => {
    const value = params[key];
    return typeof value === "string" && value !== "" ? value : null;
  };
  const template = params.template;
  return {
    template: Array.isArray(template)
      ? template
      : typeof template === "string" && template !== ""
        ? [template]
        : [],
    reason: one("reason"),
    recipient_id: one("recipient_id"),
    recipient: one("recipient"),
    project_id: one("project_id"),
    since: one("from"),
    until: one("to"),
    q: one("q"),
    dry_run: dryRun,
  };
};

/** «Отправить неушедшие»: предпросмотр и запуск; после запуска журнал перечитывается. */
export const useResendMailBatch = () => {
  const invalidate = useInvalidateMailLog();
  return useMutation({
    mutationFn: (body: MailLogResendBatchRequest) =>
      mailLogApi.resendBatch(body),
    onSuccess: (result) => {
      if (result.started) void invalidate();
    },
  });
};
