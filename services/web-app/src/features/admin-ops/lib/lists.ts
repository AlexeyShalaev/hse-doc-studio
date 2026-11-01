import { useListQueryState, type ListQueryState } from "@shared/lib";
import type { DataTablePagination } from "@shared/ui";
import { statusOf, type ViewStatus } from "./viewStatus";
import { JOB_KINDS, JOB_STATES } from "./jobs";
import { RUNNER_STATUSES } from "./runnerStatus";

// Состояние списков эксплуатации в адресе страницы (единый контракт списков):
// поиск, фильтры, сортировка и страница. Имена фильтров совпадают с
// параметрами запроса сервера. Два списка на вкладке «Раннеры» разведены
// приставкой: у токенов ключи вида t.q, t.status.

export const RUNNER_SORT = [
  "name",
  "status",
  "last_seen_at",
  "created_at",
  "version",
] as const;
export type RunnerSort = (typeof RUNNER_SORT)[number];
export type RunnerFilter = "status" | "tag" | "resource_class" | "outdated";

const RUNNER_LIST = {
  filters: {
    status: { multi: true, values: RUNNER_STATUSES },
    tag: {},
    resource_class: {},
    outdated: { values: ["true", "false"] },
  },
  sort: { fields: RUNNER_SORT, default: "status" },
} as const;

export const useRunnerListState = (): ListQueryState<
  RunnerFilter,
  RunnerSort
> => useListQueryState<RunnerFilter, RunnerSort>(RUNNER_LIST);

export const TOKEN_STATUSES = [
  "active",
  "expired",
  "exhausted",
  "revoked",
] as const;
export const TOKEN_SORT = ["created_at", "expires_at", "label"] as const;
export type TokenSort = (typeof TOKEN_SORT)[number];
export type TokenFilter = "status";

// Токенов немного и они под таблицей раннеров: страница короче.
export const TOKEN_PAGE_SIZES: readonly number[] = [10, 25, 50];

const TOKEN_LIST = {
  prefix: "t.",
  filters: { status: { values: TOKEN_STATUSES } },
  sort: { fields: TOKEN_SORT, default: "-created_at" },
  pageSize: 10,
  pageSizes: TOKEN_PAGE_SIZES,
} as const;

export const useTokenListState = (): ListQueryState<TokenFilter, TokenSort> =>
  useListQueryState<TokenFilter, TokenSort>(TOKEN_LIST);

export const RUNNER_SCOPES = ["shared", "personal"] as const;

export type QueueFilter =
  | "state"
  | "kind"
  | "user_id"
  | "org_id"
  | "project_id"
  | "runner_id"
  | "runner_scope"
  | "from"
  | "to";

const QUEUE_LIST = {
  mode: "cursor",
  filters: {
    state: { multi: true, values: JOB_STATES },
    kind: { multi: true, values: JOB_KINDS },
    user_id: {},
    org_id: {},
    project_id: {},
    runner_id: {},
    runner_scope: { values: RUNNER_SCOPES },
    from: { date: "from" },
    to: { date: "to" },
  },
} as const;

export const useQueueListState = (): ListQueryState<QueueFilter, never> =>
  useListQueryState<QueueFilter>(QUEUE_LIST);

export const OWNER_SORT = ["projects", "bytes", "name"] as const;
export type OwnerSort = (typeof OWNER_SORT)[number];
export type OwnerFilter = "kind";
export const OWNER_KINDS = ["user", "org"] as const;

const OWNER_LIST = {
  filters: { kind: { values: OWNER_KINDS } },
  sort: { fields: OWNER_SORT, default: "-projects" },
  pageSize: 25,
} as const;

export const useOwnerListState = (): ListQueryState<OwnerFilter, OwnerSort> =>
  useListQueryState<OwnerFilter, OwnerSort>(OWNER_LIST);

/** Страница серверного списка, как её видит экран. */
export type ListView<T, F extends string, S extends string> = {
  /** Первая загрузка: ready, когда хоть одна страница пришла. */
  status: ViewStatus;
  items: readonly T[];
  total: number;
  /** Идёт запрос, на экране прежние строки. */
  fetching: boolean;
  /** Последний запрос не удался (строки могут остаться от прошлого). */
  failed: boolean;
  state: ListQueryState<F, S>;
  pagination: DataTablePagination;
  onRetry?: (() => void) | undefined;
};

/** Вид списка из useServerList и его состояния в адресе. */
export const listView = <T, F extends string, S extends string>(
  list: {
    query: { data: unknown; isError: boolean; error: unknown };
    items: T[];
    total: number;
    isFetching: boolean;
    isError: boolean;
    pagination: DataTablePagination;
    refetch: () => unknown;
  },
  state: ListQueryState<F, S>,
): ListView<T, F, S> => ({
  status: statusOf(list.query),
  items: list.items,
  total: list.total,
  fetching: list.isFetching,
  failed: list.isError,
  state,
  pagination: list.pagination,
  onRetry: () => {
    void list.refetch();
  },
});
