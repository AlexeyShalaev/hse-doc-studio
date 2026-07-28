import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";

export const InstalledFontSchema = z.object({
  name: z.string(),
  size_bytes: z.number().int().nonnegative(),
  family: z.string().default(""),
});

export type InstalledFont = z.infer<typeof InstalledFontSchema>;

export const FontsListResponseSchema = z.object({
  fonts: z.array(InstalledFontSchema),
});

export type FontsListResponse = z.infer<typeof FontsListResponseSchema>;

export const FontCatalogItemSchema = z.object({
  id: z.string(),
  label: z.string(),
  family: z.string(),
  description: z.string(),
  license: z.string(),
  file_count: z.number().int().nonnegative(),
  installed: z.boolean(),
});

export type FontCatalogItem = z.infer<typeof FontCatalogItemSchema>;

export const FontCatalogResponseSchema = z.object({
  items: z.array(FontCatalogItemSchema),
});

export type FontCatalogResponse = z.infer<typeof FontCatalogResponseSchema>;

export const InstallFontResponseSchema = z.object({
  installed: z.array(InstalledFontSchema),
});

export type InstallFontResponse = z.infer<typeof InstallFontResponseSchema>;

export const SystemFontSchema = z.object({
  name: z.string(),
  path: z.string(),
  family: z.string(),
  already_installed: z.boolean(),
});

export type SystemFont = z.infer<typeof SystemFontSchema>;

export const SystemFontsListResponseSchema = z.object({
  available: z.boolean(),
  fonts: z.array(SystemFontSchema),
});

export type SystemFontsListResponse = z.infer<
  typeof SystemFontsListResponseSchema
>;

export const MarketplaceFontSchema = z.object({
  id: z.string(),
  family: z.string(),
  category: z.string(),
  cyrillic: z.boolean(),
  file_count: z.number().int().nonnegative(),
});

export type MarketplaceFont = z.infer<typeof MarketplaceFontSchema>;

export const MarketplaceSearchResponseSchema = z.object({
  total: z.number().int().nonnegative(),
  items: z.array(MarketplaceFontSchema),
});

export type MarketplaceSearchResponse = z.infer<
  typeof MarketplaceSearchResponseSchema
>;

export type MarketplaceSearchParams = {
  q: string;
  category: string | null;
  cyrillic: boolean;
  limit: number;
};

export const fontsApi = {
  list: () => apiClient.get(`/fonts`).then(parseResp(FontsListResponseSchema)),

  // Direct URL to a managed font's bytes (served by GET /fonts/{name}/file).
  // Used as the @font-face source so the UI can preview installed fonts. The
  // optional `version` (e.g. the file's size) busts the browser cache when a
  // font is replaced under the same filename, so the preview never goes stale.
  fileUrl: (name: string, version?: string | number): string => {
    const base = `${env.VITE_API_BASE_URL}/api/v1/fonts/${encodeURIComponent(name)}/file`;
    return version === undefined
      ? base
      : `${base}?v=${encodeURIComponent(String(version))}`;
  },

  catalog: () =>
    apiClient.get(`/fonts/catalog`).then(parseResp(FontCatalogResponseSchema)),

  installFromCatalog: (id: string) =>
    apiClient
      .post(`/fonts/catalog/${encodeURIComponent(id)}`)
      .then(parseResp(InstallFontResponseSchema)),

  // Raw binary body (mirrors the files PUT endpoint); the filename rides in the
  // path. axios sends a File/Blob as-is, so the backend reads request.body() bytes.
  upload: (file: File) =>
    apiClient
      .put(`/fonts/${encodeURIComponent(file.name)}`, file, {
        headers: { "Content-Type": "application/octet-stream" },
      })
      .then(parseResp(InstalledFontSchema)),

  remove: (name: string) =>
    apiClient.delete(`/fonts/${encodeURIComponent(name)}`).then(() => name),

  systemFonts: () =>
    apiClient
      .get(`/fonts/system`)
      .then(parseResp(SystemFontsListResponseSchema)),

  importSystemFonts: (paths: string[]) =>
    apiClient
      .post(`/fonts/system/import`, { paths })
      .then(parseResp(InstallFontResponseSchema)),

  marketplaceSearch: (params: MarketplaceSearchParams) =>
    apiClient
      .get(`/fonts/marketplace`, {
        params: {
          q: params.q,
          cyrillic: params.cyrillic,
          limit: params.limit,
          ...(params.category ? { category: params.category } : {}),
        },
      })
      .then(parseResp(MarketplaceSearchResponseSchema)),

  installMarketplace: (id: string) =>
    apiClient
      .post(`/fonts/marketplace/${encodeURIComponent(id)}`)
      .then(parseResp(InstallFontResponseSchema)),
};
