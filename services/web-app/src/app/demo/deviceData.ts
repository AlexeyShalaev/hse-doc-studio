import type {
  Device,
  DevicesOverview,
  ProjectStudios,
  StudioLink,
} from "@entities/connected-device";
import type { LocalBuilds, ProjectBuilds } from "@entities/project-build";

// Данные демо подключённых Студий: одни и те же для облака и локальной Студии, чтобы галереи и тесты видели
// согласованные состояния. Времена считаются от «сейчас», как у живого сервера.

const minutesAgo = (minutes: number): string =>
  new Date(Date.now() - minutes * 60_000).toISOString();

export const DEMO_DEVICE_ID = "e1123c9cadb64dafd48432897072a826";
export const DEMO_RUNNER_ID = "5f9f8fde104348e29d9b17298d93152c";

export const demoDevice = (overrides: Partial<Device> = {}): Device => ({
  id: DEMO_DEVICE_ID,
  name: "MacBook Анны",
  version: "0.5.0",
  os: "macos",
  presence: "online",
  last_seen_at: minutesAgo(0),
  activity: "idle",
  projects_count: 2,
  runner: {
    id: DEMO_RUNNER_ID,
    name: "MacBook Анны",
    state: "online",
    tags: ["ai", "pack", "tex", "verify"],
    concurrency: 1,
    running_jobs: 0,
    busy: false,
  },
  ai: {
    state: "no_provider",
    endpoints: [
      {
        name: "ollama",
        flavor: "ollama",
        reachable: true,
        models: ["qwen3:4b-instruct", "qwen3:4b-instruct-16k"],
        provider_id: null,
        provider_name: null,
        state: "no_provider",
      },
    ],
  },
  project: {
    sync: "synced",
    ahead: 0,
    behind: 0,
    last_sync_at: minutesAgo(4),
    auto_sync: true,
    pdf: { doc_id: "tz", at: minutesAgo(12), ok: true, code: null },
  },
  ...overrides,
});

export const demoOfflineDevice = (): Device =>
  demoDevice({
    id: "0b4c7a1e2d3f4a5b8c9d0e1f2a3b4c5d",
    name: "Рабочий ПК",
    os: "windows",
    presence: "offline",
    last_seen_at: minutesAgo(125),
    activity: "idle",
    runner: null,
    ai: { state: "studio_offline", endpoints: [] },
    project: null,
  });

export const demoProjectStudios = (): ProjectStudios => ({
  online_window_s: 180,
  mine: [demoDevice()],
  others: [{ user_id: "u_boris", name: "Борис Смирнов" }],
});

export const demoAccountDevices = () => ({
  online_window_s: 180,
  items: [demoDevice({ project: null }), demoOfflineDevice()],
});

export const demoCloudBuilds = (): ProjectBuilds => ({
  head: "9f2c1e7a4b0d",
  dirty: false,
  max_pdf_bytes: 104_857_600,
  documents: [
    {
      doc_id: "tz",
      cloud: {
        at: minutesAgo(5),
        commit: "9f2c1e7a4b0d",
        pages: 14,
        fresh: true,
        sha256: "a".repeat(64),
        size: 812_000,
      },
      cloud_running: false,
      cloud_failed_at: null,
      studio: null,
    },
    {
      doc_id: "vkr",
      cloud: null,
      cloud_running: false,
      cloud_failed_at: null,
      studio: {
        at: minutesAgo(40),
        commit: "11d0aa77c3e2",
        pages: 52,
        fresh: false,
        sha256: "b".repeat(64),
        size: 3_400_000,
        artifact_id: "art1",
        by_name: "Анна Петрова",
      },
    },
    {
      doc_id: "annotation",
      cloud: null,
      cloud_running: false,
      cloud_failed_at: null,
      studio: null,
    },
  ],
});

const overview = (device: Device | null): DevicesOverview => ({
  online_window_s: 180,
  device,
  others: [{ user_id: "u_boris", name: "Борис Смирнов" }],
});

export const demoStudioLink = (projectId: string | null): StudioLink => ({
  device: {
    device_id: DEMO_DEVICE_ID,
    name: "MacBook Анны",
    default_name: "MacBook-Air-Anna",
    custom: true,
  },
  runner: {
    state: "online",
    paired: true,
    name: "MacBook Анны",
    running_jobs: 0,
    enabled: true,
  },
  endpoints: [
    {
      name: "ollama",
      flavor: "ollama",
      announced: true,
      reachable: true,
      models: ["qwen3:4b-instruct", "qwen3:4b-instruct-16k"],
    },
  ],
  servers: [
    {
      credential_id: "cred_studio_ok",
      server_url: "https://studio.example.org",
      host: "studio.example.org",
      state: "ok",
      account_name: "Анна Петрова",
      last: {
        at: minutesAgo(1),
        ok: true,
        code: null,
        interval_s: 60,
        online_window_s: 180,
      },
      cloud: overview(demoDevice()),
      cloud_error: null,
    },
  ],
  project: projectId === null ? null : demoDevice().project,
});

export const demoLocalBuilds = (): LocalBuilds => ({
  connected: true,
  cloud_error: null,
  local_head: "9f2c1e7a4b0d",
  local_dirty: false,
  cloud_head: "9f2c1e7a4b0d",
  documents: [
    {
      doc_id: "tz",
      local: null,
      cloud: {
        at: minutesAgo(5),
        commit: "9f2c1e7a4b0d",
        pages: 14,
        fresh: true,
        sha256: "a".repeat(64),
        size: 812_000,
      },
      cloud_running: false,
      studio: null,
      relation: "cloud_only",
      can_fetch: true,
    },
    {
      doc_id: "vkr",
      local: {
        at: minutesAgo(40),
        commit: "11d0aa77c3e2",
        fresh: false,
        sha256: "b".repeat(64),
        pages: 52,
        from_cloud: false,
      },
      cloud: null,
      cloud_running: false,
      studio: null,
      relation: "local_only",
      can_fetch: false,
    },
    {
      doc_id: "annotation",
      local: {
        at: minutesAgo(90),
        commit: "9f2c1e7a4b0d",
        fresh: true,
        sha256: "c".repeat(64),
        pages: 2,
        from_cloud: true,
      },
      cloud: {
        at: minutesAgo(90),
        commit: "9f2c1e7a4b0d",
        pages: 2,
        fresh: true,
        sha256: "c".repeat(64),
        size: 60_000,
      },
      cloud_running: false,
      studio: null,
      relation: "same",
      can_fetch: false,
    },
  ],
});
