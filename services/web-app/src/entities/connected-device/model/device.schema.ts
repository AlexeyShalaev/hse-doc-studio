import { z } from "zod";

// Контракт подключённых Студий (docs/design/connected-devices.md): сервер отдаёт только метаданные состояния.

export const DEVICE_PRESENCE = ["online", "offline"] as const;
export const DeviceActivitySchema = z.enum(["idle", "syncing", "building"]);
export type DeviceActivity = z.infer<typeof DeviceActivitySchema>;

export const DeviceOsSchema = z.enum(["macos", "windows", "linux", "other"]);
export type DeviceOs = z.infer<typeof DeviceOsSchema>;

export const SyncCodeSchema = z.enum([
  "synced",
  "syncing",
  "ahead",
  "behind",
  "diverged",
  "conflicts",
  "offline",
  "auth_failed",
  "blocked",
  "error",
  "unfetched",
]);
export type SyncCode = z.infer<typeof SyncCodeSchema>;

/** Доступна ли модель через эту Студию облаку и, если нет, почему: по коду интерфейс даёт совет. */
export const AiStateSchema = z.enum([
  "ready",
  "not_opened",
  "runner_unpaired",
  "runner_offline",
  "runner_paused",
  "runner_revoked",
  "disabled",
  "endpoint_unreachable",
  "no_models",
  "no_provider",
  "studio_offline",
  "unknown",
]);
export type AiState = z.infer<typeof AiStateSchema>;

export const DeviceRunnerSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  state: z.enum([
    "online",
    "stale",
    "offline",
    "paused",
    "revoked",
    "disabled",
  ]),
  tags: z.array(z.string()),
  concurrency: z.number().int(),
  running_jobs: z.number().int(),
  busy: z.boolean(),
});
export type DeviceRunner = z.infer<typeof DeviceRunnerSchema>;

export const DeviceEndpointSchema = z.strictObject({
  name: z.string(),
  flavor: z.enum(["openai", "ollama"]),
  reachable: z.boolean().nullable(),
  models: z.array(z.string()),
  provider_id: z.string().nullable(),
  provider_name: z.string().nullable(),
  state: AiStateSchema,
});
export type DeviceEndpoint = z.infer<typeof DeviceEndpointSchema>;

export const DeviceAiSchema = z.strictObject({
  state: AiStateSchema,
  endpoints: z.array(DeviceEndpointSchema),
});
export type DeviceAi = z.infer<typeof DeviceAiSchema>;

export const DevicePdfSchema = z.strictObject({
  doc_id: z.string(),
  at: z.string(),
  ok: z.boolean(),
  code: z.string().nullable(),
});

export const DeviceProjectSchema = z.strictObject({
  sync: SyncCodeSchema,
  ahead: z.number().int(),
  behind: z.number().int(),
  last_sync_at: z.string().nullable(),
  auto_sync: z.boolean(),
  pdf: DevicePdfSchema.nullable(),
});
export type DeviceProject = z.infer<typeof DeviceProjectSchema>;

export const DeviceSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  version: z.string(),
  os: DeviceOsSchema,
  presence: z.enum(DEVICE_PRESENCE),
  last_seen_at: z.string(),
  activity: DeviceActivitySchema,
  projects_count: z.number().int(),
  runner: DeviceRunnerSchema.nullable(),
  ai: DeviceAiSchema,
  project: DeviceProjectSchema.nullable(),
});
export type Device = z.infer<typeof DeviceSchema>;

export const WorkingLocallySchema = z.strictObject({
  user_id: z.string(),
  name: z.string(),
});
export type WorkingLocally = z.infer<typeof WorkingLocallySchema>;

/** Студии проекта: свои целиком, чужие одной строкой «работает локально» (без имени машины и деталей). */
export const ProjectStudiosSchema = z.strictObject({
  online_window_s: z.number().int(),
  mine: z.array(DeviceSchema),
  others: z.array(WorkingLocallySchema),
});
export type ProjectStudios = z.infer<typeof ProjectStudiosSchema>;

export const AccountDevicesSchema = z.strictObject({
  online_window_s: z.number().int(),
  items: z.array(DeviceSchema),
});
export type AccountDevices = z.infer<typeof AccountDevicesSchema>;

/** Как облако видит эту Студию: ответ сервера локальной Студии. */
export const DevicesOverviewSchema = z.strictObject({
  online_window_s: z.number().int(),
  device: DeviceSchema.nullable(),
  others: z.array(WorkingLocallySchema),
});
export type DevicesOverview = z.infer<typeof DevicesOverviewSchema>;

// Локальная Студия (`/device`, `/git/studio-link`).
export const LocalDeviceSchema = z.strictObject({
  device_id: z.string(),
  name: z.string(),
  default_name: z.string(),
  custom: z.boolean(),
});
export type LocalDevice = z.infer<typeof LocalDeviceSchema>;

export const LocalRunnerSchema = z.strictObject({
  state: z.string(),
  paired: z.boolean(),
  name: z.string().nullable(),
  running_jobs: z.number().int(),
  enabled: z.boolean(),
});
export type LocalRunner = z.infer<typeof LocalRunnerSchema>;

export const LocalEndpointSchema = z.strictObject({
  name: z.string(),
  flavor: z.enum(["openai", "ollama"]),
  announced: z.boolean(),
  reachable: z.boolean().nullable(),
  models: z.array(z.string()),
});
export type LocalEndpoint = z.infer<typeof LocalEndpointSchema>;

export const LastPresenceSchema = z.strictObject({
  at: z.string(),
  ok: z.boolean(),
  code: z.string().nullable(),
  interval_s: z.number().int(),
  online_window_s: z.number().int(),
});
export type LastPresence = z.infer<typeof LastPresenceSchema>;

export const LINK_SERVER_STATE = [
  "ok",
  "expired",
  "revoked",
  "unreachable",
] as const;
export const LinkServerSchema = z.strictObject({
  credential_id: z.string(),
  server_url: z.string(),
  host: z.string(),
  state: z.enum(LINK_SERVER_STATE),
  account_name: z.string().nullable(),
  last: LastPresenceSchema.nullable(),
  cloud: DevicesOverviewSchema.nullable(),
  cloud_error: z.string().nullable(),
});
export type LinkServer = z.infer<typeof LinkServerSchema>;

export const StudioLinkSchema = z.strictObject({
  device: LocalDeviceSchema,
  runner: LocalRunnerSchema,
  endpoints: z.array(LocalEndpointSchema),
  servers: z.array(LinkServerSchema),
  project: DeviceProjectSchema.nullable(),
});
export type StudioLink = z.infer<typeof StudioLinkSchema>;
