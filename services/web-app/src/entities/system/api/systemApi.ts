import axios from "axios";
import { z } from "zod";
import { env } from "@shared/config";
import { useThemeStore } from "@shared/lib";

export const RunnerHealthSchema = z.object({
  docker: z.enum(["running", "stopped"]),
});

export type RunnerHealth = z.infer<typeof RunnerHealthSchema>;

export const EditorEntrySchema = z.object({
  id: z.enum(["cursor", "vscode"]),
  label: z.string(),
  scheme: z.string(),
  available: z.boolean(),
});

export const EditorsResponseSchema = z.object({
  os: z.enum(["windows", "macos", "linux", "other"]),
  editors: z.array(EditorEntrySchema),
});

export type EditorEntry = z.infer<typeof EditorEntrySchema>;
export type EditorsResponse = z.infer<typeof EditorsResponseSchema>;

export const ArchiveFormatSchema = z.object({
  id: z.enum(["zip", "targz", "7z", "rar"]),
  label: z.string(),
  ext: z.string(),
  available: z.boolean(),
});

export const ArchiveFormatsResponseSchema = z.object({
  formats: z.array(ArchiveFormatSchema),
});

export type ArchiveFormat = z.infer<typeof ArchiveFormatSchema>;
export type ArchiveFormatId = ArchiveFormat["id"];
export type ArchiveFormatsResponse = z.infer<
  typeof ArchiveFormatsResponseSchema
>;

export const SystemInfoSchema = z.object({
  version: z.string(),
  deployment_mode: z.enum(["all-in-one", "standard", "native"]),
  os: z.enum(["windows", "macos", "linux", "other"]),
  os_version: z.string(),
  python_version: z.string(),
  image_ref: z.string().nullable(),
  source_url: z.string(),
  github_repo: z.string(),
  license: z.string(),
  docker: z.enum(["running", "stopped"]),
  can_self_update: z.boolean(),
  // Absolute path of the app data dir (global config). Optional so an older,
  // not-yet-restarted backend that omits it doesn't break the About screen.
  data_dir: z.string().optional(),
  // ISO-8601 build timestamp baked into the image by CI; "" for a source run.
  built: z.string().default(""),
  // Update state from the last check, served from the backend's cache — no
  // network happens on this call. Defaults keep the About screen working
  // against a backend that hasn't been restarted yet (it runs without reload).
  latest_version: z.string().default(""),
  update_available: z.boolean().default(false),
  update_checked_at: z.string().nullish(),
  update_feed_enabled: z.boolean().default(true),
  // What the available version brings, as the last check found it. The curated
  // notes below only describe versions this build ships with, so for a pending
  // update these (cached backend-side) are the only ones that exist.
  latest_release_date: z.string().default(""),
  latest_release_notes: z.array(z.string()).default([]),
});

export type SystemInfo = z.infer<typeof SystemInfoSchema>;

export const ReleaseEntrySchema = z.object({
  version: z.string(),
  date: z.string(),
  notes: z.array(z.string()),
});

export const ReleaseNotesResponseSchema = z.object({
  releases: z.array(ReleaseEntrySchema),
});

export type ReleaseEntry = z.infer<typeof ReleaseEntrySchema>;
export type ReleaseNotesResponse = z.infer<typeof ReleaseNotesResponseSchema>;

export const VersionOptionSchema = z.object({
  version: z.string(),
  date: z.string(),
  notes: z.array(z.string()),
  installed: z.boolean(),
  // Новее установленной; иначе переключение на неё — откат назад.
  newer: z.boolean(),
});

export const VersionsResponseSchema = z.object({
  current: z.string(),
  checked_at: z.string().nullish(),
  versions: z.array(VersionOptionSchema),
});

export type VersionOption = z.infer<typeof VersionOptionSchema>;
export type VersionsResponse = z.infer<typeof VersionsResponseSchema>;

export const CheckUpdatesResponseSchema = z.object({
  current: z.string(),
  latest: z.string(),
  available: z.boolean(),
  // false → the feed didn't answer (disabled / unreachable / rate-limited);
  // `latest` is then the last known value and `reason` explains it.
  checked: z.boolean(),
  checked_at: z.string().nullish(),
  reason: z.string(),
});

export type CheckUpdatesResponse = z.infer<typeof CheckUpdatesResponseSchema>;

export const SelfUpdateResponseSchema = z.object({
  started: z.boolean(),
  target_image: z.string(),
});

export type SelfUpdateResponse = z.infer<typeof SelfUpdateResponseSchema>;

// Bypass the shared apiClient interceptor on purpose: the runner-health
// endpoint is polled on a timer and we don't want a global toast every few
// seconds when docker is stopped or the backend is unreachable. We reuse the
// same client for editors for consistency.
const systemClient = axios.create({
  baseURL: `${env.VITE_API_BASE_URL}/api/v1`,
  timeout: 5_000,
});

// Release notes are localized server-side, so this client needs the same
// interface-language header the shared apiClient sends. Read live from the
// store (not a hook) so it always reflects the user's latest choice.
systemClient.interceptors.request.use((config) => {
  config.headers.set("X-Interface-Language", useThemeStore.getState().lang);
  return config;
});

// The update check talks to an external release feed through the backend, whose
// own feed timeout is 8s — the 5s client default would abort first and report a
// failure the backend was about to answer.
const UPDATE_CHECK_TIMEOUT_MS = 20_000;

export const systemApi = {
  getRunnerHealth: async (): Promise<RunnerHealth> => {
    const res = await systemClient.get("/system/runner-health");
    return RunnerHealthSchema.parse(res.data);
  },

  getEditors: async (): Promise<EditorsResponse> => {
    const res = await systemClient.get("/system/editors");
    return EditorsResponseSchema.parse(res.data);
  },

  getArchiveFormats: async (): Promise<ArchiveFormatsResponse> => {
    const res = await systemClient.get("/system/archive-formats");
    return ArchiveFormatsResponseSchema.parse(res.data);
  },

  getSystemInfo: async (): Promise<SystemInfo> => {
    const res = await systemClient.get("/system/info");
    return SystemInfoSchema.parse(res.data);
  },

  // Curated bilingual release notes — local data on the backend, no network.
  getReleaseNotes: async (): Promise<ReleaseNotesResponse> => {
    const res = await systemClient.get("/system/release-notes");
    return ReleaseNotesResponseSchema.parse(res.data);
  },

  // Versions this install can switch to, from the backend's cache of the last
  // feed check (no network on this call).
  getVersions: async (): Promise<VersionsResponse> => {
    const res = await systemClient.get("/system/versions");
    return VersionsResponseSchema.parse(res.data);
  },

  // Asks the release feed for the newest version and caches the answer
  // backend-side (shared by every tab, survives a reload).
  checkUpdates: async (): Promise<CheckUpdatesResponse> => {
    const res = await systemClient.post("/system/check-updates", undefined, {
      timeout: UPDATE_CHECK_TIMEOUT_MS,
    });
    return CheckUpdatesResponseSchema.parse(res.data);
  },

  // Fire-and-forget: returns 202 once the detached updater container is
  // launched. The backend is then recreated and goes offline mid-update, so
  // the caller must poll getSystemInfo() for recovery (see useSelfUpdate).
  selfUpdate: async (version: string): Promise<SelfUpdateResponse> => {
    const res = await systemClient.post("/system/self-update", { version });
    return SelfUpdateResponseSchema.parse(res.data);
  },
};
