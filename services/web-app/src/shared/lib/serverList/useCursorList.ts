import { useEffect, useMemo, useState } from "react";
import {
  keepPreviousData,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import type { ListStateCore } from "./useServerList";
import type { CursorPage, ListRequestParams } from "./types";

// Журнал с дописыванием (аудит, очередь): первая страница, затем «Показать ещё»
// по next_cursor, страницы копятся. limit не наращивается: на 200 это ломается.
//
// Опрос (pollMs) перечитывает только первую страницу и вклеивает её сверху:
// строки, уже видные ниже, остаются, свежие версии строк заменяют старые.
// Если новых строк больше страницы и стык не найден, список начинается заново
// с первой страницы, иначе между ними была бы дыра.

export type CursorListOptions<T> = {
  state: Pick<ListStateCore, "params">;
  queryKey: readonly unknown[];
  fetchPage: (
    params: ListRequestParams & { cursor?: string },
    signal: AbortSignal,
  ) => Promise<CursorPage<T>>;
  /** Идентификатор строки: по нему склеиваются страницы. */
  getId: (row: T) => string;
  /** Опрос первой страницы, мс. */
  pollMs?: number;
  enabled?: boolean;
};

/** То, что принимает Pagination в режиме курсора. */
export type CursorPaginationState = {
  mode: "cursor";
  shown: number;
  hasMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
  totalEstimate: number | null;
};

type Pages<T> = InfiniteData<CursorPage<T>, string | null>;

/** Вклеивает свежую первую страницу над уже загруженными. */
export const mergeHead = <T>(
  old: Pages<T> | undefined,
  head: CursorPage<T>,
  getId: (row: T) => string,
): Pages<T> => {
  const fresh: Pages<T> = { pages: [head], pageParams: [null] };
  if (!old || old.pages.length < 2) return fresh;
  const last = head.items[head.items.length - 1];
  if (!last) return fresh;
  const loaded = old.pages.flatMap((p) => p.items);
  const joint = loaded.findIndex((row) => getId(row) === getId(last));
  if (joint === -1) return fresh;
  const rest = loaded.slice(joint + 1);
  const tail = old.pages[old.pages.length - 1];
  if (rest.length === 0 || !tail) return fresh;
  return {
    pages: [head, { ...tail, items: rest }],
    // Хвост начинается сразу за последней строкой головы.
    pageParams: [null, head.next_cursor],
  };
};

export const useCursorList = <T>({
  state,
  queryKey,
  fetchPage,
  getId,
  pollMs,
  enabled = true,
}: CursorListOptions<T>) => {
  const client = useQueryClient();
  const key = useMemo(
    () => [...queryKey, "log", state.params] as const,
    [queryKey, state.params],
  );
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam, signal }) =>
      fetchPage(
        pageParam ? { ...state.params, cursor: pageParam } : state.params,
        signal,
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
    staleTime: 0,
    enabled,
  });

  const ready = query.data !== undefined && !query.isPlaceholderData;
  const head = useQuery({
    queryKey: [...queryKey, "log", state.params, "head"],
    queryFn: ({ signal }) => fetchPage(state.params, signal),
    enabled: enabled && ready && pollMs !== undefined,
    refetchInterval: pollMs ?? false,
    // Первый опрос через pollMs, а не сразу: первая страница только что пришла.
    staleTime: pollMs ?? 0,
    initialData: () => query.data?.pages[0],
    initialDataUpdatedAt: () => query.dataUpdatedAt,
  });

  const headData = head.data;
  useEffect(() => {
    if (!headData || pollMs === undefined) return;
    const current = client.getQueryData<Pages<T>>(key);
    if (current?.pages[0] === headData) return;
    client.setQueryData<Pages<T>>(key, (old) =>
      mergeHead(old, headData, getId),
    );
  }, [headData, pollMs, client, key, getId]);

  const items = useMemo(() => {
    const seen = new Set<string>();
    const out: T[] = [];
    for (const page of query.data?.pages ?? []) {
      for (const row of page.items) {
        const id = getId(row);
        if (seen.has(id)) continue;
        seen.add(id);
        out.push(row);
      }
    }
    return out;
  }, [query.data, getId]);

  // «Обновить» перечитывает только первую страницу и вклеивает её, как опрос:
  // refetch бесконечного запроса прошёл бы заново все подгруженные страницы.
  const [refreshing, setRefreshing] = useState(false);
  const refresh = async () => {
    if (!query.data || query.isError) {
      await query.refetch();
      return;
    }
    setRefreshing(true);
    try {
      const fresh = await client.fetchQuery({
        queryKey: [...queryKey, "log", state.params, "refresh"],
        queryFn: ({ signal }) => fetchPage(state.params, signal),
        staleTime: 0,
      });
      client.setQueryData<Pages<T>>(key, (old) => mergeHead(old, fresh, getId));
    } finally {
      setRefreshing(false);
    }
  };

  const totalEstimate = query.data?.pages[0]?.total_estimate ?? null;
  const loadMore = () => {
    if (query.hasNextPage && !query.isFetchingNextPage) {
      void query.fetchNextPage();
    }
  };

  const pagination: CursorPaginationState = {
    mode: "cursor",
    shown: items.length,
    hasMore: query.hasNextPage,
    onLoadMore: loadMore,
    loading: query.isFetchingNextPage,
    totalEstimate,
  };

  return {
    query,
    items,
    hasMore: query.hasNextPage,
    loadMore,
    isLoadingMore: query.isFetchingNextPage,
    isLoading: query.isPending,
    isFetching: query.isFetching || refreshing,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    /** Свежая первая страница поверх загруженных (кнопка «Обновить»). */
    refresh,
    totalEstimate,
    pagination,
  };
};
