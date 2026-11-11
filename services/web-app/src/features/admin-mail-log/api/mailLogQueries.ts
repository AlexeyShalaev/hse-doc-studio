import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import {
  useCursorList,
  type ListQueryState,
  type ListStateOptions,
} from "@shared/lib";
import { mailLogApi } from "./mailLogApi";
import { MAIL_STATUSES, type MailLogEntry } from "./schemas";

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
