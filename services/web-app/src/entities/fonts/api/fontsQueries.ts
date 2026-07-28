import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  fontsApi,
  type FontCatalogResponse,
  type FontsListResponse,
  type InstallFontResponse,
  type InstalledFont,
  type MarketplaceSearchParams,
  type MarketplaceSearchResponse,
  type SystemFontsListResponse,
} from "./fontsApi";

export const fontsKeys = {
  all: ["fonts"] as const,
  list: () => [...fontsKeys.all, "list"] as const,
  catalog: () => [...fontsKeys.all, "catalog"] as const,
  system: () => [...fontsKeys.all, "system"] as const,
  marketplace: (params: MarketplaceSearchParams) =>
    [...fontsKeys.all, "marketplace", params] as const,
};

export const useFonts = () =>
  useQuery<FontsListResponse>({
    queryKey: fontsKeys.list(),
    queryFn: () => fontsApi.list(),
    staleTime: 5_000,
  });

export const useFontCatalog = () =>
  useQuery<FontCatalogResponse>({
    queryKey: fontsKeys.catalog(),
    queryFn: () => fontsApi.catalog(),
    staleTime: 60_000,
  });

// Scanning the OS font dirs is only needed when the picker is open, so this
// query is gated by `enabled`.
export const useSystemFonts = (enabled: boolean) =>
  useQuery<SystemFontsListResponse>({
    queryKey: fontsKeys.system(),
    queryFn: () => fontsApi.systemFonts(),
    enabled,
    staleTime: 60_000,
  });

// Catalog/system "installed" flags derive from the installed list, so every
// mutation refreshes all three queries.
const useInvalidateFonts = () => {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: fontsKeys.list() });
    void queryClient.invalidateQueries({ queryKey: fontsKeys.catalog() });
    void queryClient.invalidateQueries({ queryKey: fontsKeys.system() });
  };
};

export const useUploadFont = () => {
  const invalidate = useInvalidateFonts();
  return useMutation<InstalledFont, Error, File>({
    mutationFn: (file) => fontsApi.upload(file),
    onSuccess: invalidate,
  });
};

export const useDeleteFont = () => {
  const invalidate = useInvalidateFonts();
  return useMutation<string, Error, string>({
    mutationFn: (name) => fontsApi.remove(name),
    onSuccess: invalidate,
  });
};

export const useInstallCatalogFont = () => {
  const invalidate = useInvalidateFonts();
  return useMutation<InstallFontResponse, Error, string>({
    mutationFn: (id) => fontsApi.installFromCatalog(id),
    onSuccess: invalidate,
  });
};

export const useImportSystemFonts = () => {
  const invalidate = useInvalidateFonts();
  return useMutation<InstallFontResponse, Error, string[]>({
    mutationFn: (paths) => fontsApi.importSystemFonts(paths),
    onSuccess: invalidate,
  });
};

export const useMarketplaceSearch = (params: MarketplaceSearchParams) =>
  useQuery<MarketplaceSearchResponse>({
    queryKey: fontsKeys.marketplace(params),
    queryFn: () => fontsApi.marketplaceSearch(params),
    // Keep showing the previous page while a new query/filter loads (no fl. flicker).
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });

export const useInstallMarketplaceFont = () => {
  const invalidate = useInvalidateFonts();
  return useMutation<InstallFontResponse, Error, string>({
    mutationFn: (id) => fontsApi.installMarketplace(id),
    onSuccess: invalidate,
  });
};
