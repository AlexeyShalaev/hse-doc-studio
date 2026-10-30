import { useEffect } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ListQueryState } from "./useListQueryState";
import type { ListPage, ListRequestParams } from "./types";

/** Часть состояния списка, которая нужна загрузке; не зависит от имён фильтров. */
export type ListStateCore = Pick<
  ListQueryState,
  | "params"
  | "key"
  | "page"
  | "pageSize"
  | "setPage"
  | "pageSizes"
  | "setPageSize"
>;

// Ограниченный серверный список: одна страница за запрос, total от сервера.
// Пока идёт новый запрос, на экране остаются прежние строки (без мерцания).

export type ServerListOptions<T> = {
  state: ListStateCore;
  /** Начало ключа запроса; параметры списка добавляются сами. */
  queryKey: readonly unknown[];
  fetchPage: (
    params: ListRequestParams,
    signal: AbortSignal,
  ) => Promise<ListPage<T>>;
  enabled?: boolean;
  /** Опрос, мс; по умолчанию без опроса. */
  refetchInterval?: number | false;
};

/** То, что принимают Pagination и DataTable.pagination в режиме страниц. */
export type OffsetPaginationState = {
  mode?: "offset";
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  pageSizes?: readonly number[];
  onPageSizeChange?: (size: number) => void;
  busy?: boolean;
};

export const useServerList = <T>({
  state,
  queryKey,
  fetchPage,
  enabled = true,
  refetchInterval = false,
}: ServerListOptions<T>) => {
  const query = useQuery({
    queryKey: [...queryKey, "list", state.params],
    queryFn: ({ signal }) => fetchPage(state.params, signal),
    placeholderData: keepPreviousData,
    staleTime: 0,
    enabled,
    refetchInterval,
  });

  const data = query.data;
  const total = data?.total ?? 0;
  const { page, pageSize, setPage } = state;
  // Страница за концом списка (удалили строки, ссылка устарела): на последнюю.
  useEffect(() => {
    if (!data || query.isPlaceholderData) return;
    if (data.items.length === 0 && data.total > 0 && page > 0) {
      setPage(Math.max(0, Math.ceil(data.total / pageSize) - 1), {
        replace: true,
      });
    }
  }, [data, query.isPlaceholderData, page, pageSize, setPage]);

  const pagination: OffsetPaginationState = {
    page,
    pageSize,
    total,
    onPageChange: setPage,
    pageSizes: state.pageSizes,
    onPageSizeChange: state.setPageSize,
    busy: query.isFetching,
  };

  return {
    query,
    items: data?.items ?? [],
    total,
    /** Первая загрузка: данных ещё нет. */
    isLoading: query.isPending,
    /** Любой запрос в пути, в том числе со старыми строками на экране. */
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    pagination,
  };
};
