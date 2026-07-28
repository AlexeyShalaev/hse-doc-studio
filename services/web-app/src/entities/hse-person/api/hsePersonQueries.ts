import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { hsePersonApi, type HsePersonSearchParams } from "./hsePersonApi";

const DAY_MS = 24 * 60 * 60_000;
const SEARCH_STALE_MS = 5 * 60_000;

export const hsePersonKeys = {
  all: ["hse-persons"] as const,
  facets: (campus: string) => [...hsePersonKeys.all, "facets", campus] as const,
  search: (params: HsePersonSearchParams) =>
    [...hsePersonKeys.all, "search", params] as const,
  detail: (id: string) => [...hsePersonKeys.all, "detail", id] as const,
};

// Shared factory so the per-row lazy hook and the on-pick fetch use the same
// cache entry (the profile is fetched at most once per person, then reused).
export const hsePersonDetailQuery = (id: string) => ({
  queryKey: hsePersonKeys.detail(id),
  queryFn: () => hsePersonApi.getDetail(id),
  staleTime: DAY_MS,
});

export const useHseFacets = (campus: string, enabled = true) =>
  useQuery({
    queryKey: hsePersonKeys.facets(campus),
    queryFn: () => hsePersonApi.getFacets(campus),
    staleTime: DAY_MS,
    enabled,
  });

export const useHsePersonSearch = (
  params: HsePersonSearchParams,
  enabled: boolean,
) =>
  useQuery({
    queryKey: hsePersonKeys.search(params),
    queryFn: () => hsePersonApi.search(params),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: SEARCH_STALE_MS,
  });

// Lazy per-row detail: only fires once the row scrolls into view (`enabled`).
export const useHsePersonDetail = (id: string, enabled: boolean) =>
  useQuery({
    ...hsePersonDetailQuery(id),
    enabled: enabled && id !== "",
  });
