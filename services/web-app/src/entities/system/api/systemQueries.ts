import { useQuery } from "@tanstack/react-query";
import { useThemeStore } from "@shared/lib";
import {
  systemApi,
  type ArchiveFormatsResponse,
  type EditorsResponse,
  type ReleaseNotesResponse,
  type RunnerHealth,
  type VersionsResponse,
  type SystemInfo,
} from "./systemApi";

export const systemKeys = {
  all: ["system"] as const,
  runnerHealth: () => [...systemKeys.all, "runner-health"] as const,
  editors: () => [...systemKeys.all, "editors"] as const,
  archiveFormats: () => [...systemKeys.all, "archive-formats"] as const,
  info: () => [...systemKeys.all, "info"] as const,
  // Keyed by interface language: the notes come back localized, so a language
  // switch must fetch them again instead of showing the previous language.
  releaseNotes: (lang: string) =>
    [...systemKeys.all, "release-notes", lang] as const,
  versions: () => [...systemKeys.all, "versions"] as const,
};

const RUNNER_HEALTH_POLL_MS = 30_000;

export const useRunnerHealth = () =>
  useQuery<RunnerHealth>({
    queryKey: systemKeys.runnerHealth(),
    queryFn: () => systemApi.getRunnerHealth(),
    refetchInterval: RUNNER_HEALTH_POLL_MS,
    refetchIntervalInBackground: false,
    retry: false,
    staleTime: 0,
  });

// Editor availability doesn't change without app restart (user would need to
// install/uninstall an editor). Cache aggressively; user can refresh the page
// if they need a re-detect.
export const useEditors = () =>
  useQuery<EditorsResponse>({
    queryKey: systemKeys.editors(),
    queryFn: () => systemApi.getEditors(),
    retry: false,
    staleTime: Infinity,
  });

// Like editors: which archive tools (7z/rar) are on PATH only changes if the
// user installs one and restarts. Cache for the session.
export const useArchiveFormats = () =>
  useQuery<ArchiveFormatsResponse>({
    queryKey: systemKeys.archiveFormats(),
    queryFn: () => systemApi.getArchiveFormats(),
    retry: false,
    staleTime: Infinity,
  });

// System/version info doesn't change without an app restart — cache for the
// session. Backend is local so this never needs polling. The update fields on it
// are read from the backend's cache (no outbound request), and an explicit check
// invalidates this query rather than duplicating the state.
export const useSystemInfo = () =>
  useQuery<SystemInfo>({
    queryKey: systemKeys.info(),
    queryFn: () => systemApi.getSystemInfo(),
    retry: false,
    staleTime: Infinity,
  });

// Versions available to switch to. Served from the backend's cache, so this is
// a local call; an explicit check refreshes it by invalidating this query.
export const useAppVersions = (enabled = true) =>
  useQuery<VersionsResponse>({
    queryKey: systemKeys.versions(),
    queryFn: () => systemApi.getVersions(),
    enabled,
    retry: false,
    staleTime: Infinity,
  });

// Release notes ship with the running build: they can only change on restart,
// and never depend on the network. Cache for the session, per language.
export const useReleaseNotes = (enabled = true) => {
  const lang = useThemeStore((s) => s.lang);
  return useQuery<ReleaseNotesResponse>({
    queryKey: systemKeys.releaseNotes(lang),
    queryFn: () => systemApi.getReleaseNotes(),
    enabled,
    retry: false,
    staleTime: Infinity,
  });
};
