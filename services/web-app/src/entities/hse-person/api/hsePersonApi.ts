import { apiClient, parseResp } from "@shared/api";

import {
  HseFacetsResponseSchema,
  HsePersonDetailSchema,
  HseSearchResponseSchema,
} from "./hsePersonSchemas";

export type HsePersonSearchParams = {
  q?: string;
  campus?: string;
  udept?: string;
  ltr?: string;
  category?: string;
  scirank?: string;
  position?: string;
  intst?: string;
  limit?: number;
};

// Drop empty/undefined facets so they don't clutter the request URL.
const compact = (
  params: HsePersonSearchParams,
): Record<string, string | number> => {
  const out: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === "") continue;
    out[key] = value;
  }
  return out;
};

export const hsePersonApi = {
  getFacets: (campus: string) =>
    apiClient
      .get("/hse/persons/facets", { params: { campus } })
      .then(parseResp(HseFacetsResponseSchema)),

  search: (params: HsePersonSearchParams) =>
    apiClient
      .get("/hse/persons/search", { params: compact(params) })
      .then(parseResp(HseSearchResponseSchema)),

  getDetail: (id: string) =>
    apiClient.get(`/hse/persons/${id}`).then(parseResp(HsePersonDetailSchema)),
};
