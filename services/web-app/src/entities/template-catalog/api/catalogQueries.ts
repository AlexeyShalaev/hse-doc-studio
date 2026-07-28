import { useQuery } from "@tanstack/react-query";
import { catalogApi } from "./catalogApi";

type PackList = Awaited<ReturnType<typeof catalogApi.listPacks>>;
type VersionList = Awaited<ReturnType<typeof catalogApi.listVersions>>;
type VersionDetail = Awaited<ReturnType<typeof catalogApi.getVersion>>;

export const catalogKeys = {
  all: ["catalog"] as const,
  packs: () => [...catalogKeys.all, "packs"] as const,
  versions: (packId: string, templateId: string) =>
    [...catalogKeys.all, "versions", packId, templateId] as const,
  versionDetail: (packId: string, templateId: string, version: string) =>
    [...catalogKeys.all, "version", packId, templateId, version] as const,
};

export const usePacks = () =>
  useQuery<PackList>({
    queryKey: catalogKeys.packs(),
    queryFn: () => catalogApi.listPacks(),
    staleTime: 5 * 60 * 1000,
  });

export const useVersions = (packId: string, templateId: string) =>
  useQuery<VersionList>({
    queryKey: catalogKeys.versions(packId, templateId),
    queryFn: () => catalogApi.listVersions(packId, templateId),
    enabled: !!packId && !!templateId,
    staleTime: 5 * 60 * 1000,
  });

export const useVersionDetail = (
  packId: string,
  templateId: string,
  version: string,
) =>
  useQuery<VersionDetail>({
    queryKey: catalogKeys.versionDetail(packId, templateId, version),
    queryFn: () => catalogApi.getVersion(packId, templateId, version),
    enabled: !!packId && !!templateId && !!version,
    staleTime: 5 * 60 * 1000,
  });
