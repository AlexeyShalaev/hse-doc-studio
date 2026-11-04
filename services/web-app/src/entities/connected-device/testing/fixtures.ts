import type {
  Device,
  DeviceEndpoint,
  LinkServer,
  StudioLink,
} from "../model/device.schema";

// Данные для тестов и галерей: устройство в сети с раннером и моделью, у которой в облаке нет провайдера.

export const NOW = Date.parse("2026-11-04T10:00:00Z");

export const minutesBefore = (minutes: number): string =>
  new Date(NOW - minutes * 60_000).toISOString();

export const makeEndpoint = (
  overrides: Partial<DeviceEndpoint> = {},
): DeviceEndpoint => ({
  name: "ollama",
  flavor: "ollama",
  reachable: true,
  models: ["qwen3:4b-instruct", "qwen3:4b-instruct-16k"],
  provider_id: null,
  provider_name: null,
  state: "no_provider",
  ...overrides,
});

export const makeDevice = (overrides: Partial<Device> = {}): Device => ({
  id: "e1123c9cadb64dafd48432897072a826",
  name: "MacBook Анны",
  version: "0.5.0",
  os: "macos",
  presence: "online",
  last_seen_at: minutesBefore(0),
  activity: "idle",
  projects_count: 2,
  runner: {
    id: "5f9f8fde104348e29d9b17298d93152c",
    name: "MacBook Анны",
    state: "online",
    tags: ["ai", "pack", "tex", "verify"],
    concurrency: 1,
    running_jobs: 0,
    busy: false,
  },
  ai: { state: "no_provider", endpoints: [makeEndpoint()] },
  project: {
    sync: "synced",
    ahead: 0,
    behind: 0,
    last_sync_at: minutesBefore(4),
    auto_sync: true,
    pdf: { doc_id: "tz", at: minutesBefore(12), ok: true, code: null },
  },
  ...overrides,
});

export const makeServer = (
  overrides: Partial<LinkServer> = {},
): LinkServer => ({
  credential_id: "cred1",
  server_url: "https://studio.example.org",
  host: "studio.example.org",
  state: "ok",
  account_name: "Анна Петрова",
  last: {
    at: minutesBefore(1),
    ok: true,
    code: null,
    interval_s: 60,
    online_window_s: 180,
  },
  cloud: {
    online_window_s: 180,
    device: makeDevice(),
    others: [{ user_id: "u2", name: "Борис Смирнов" }],
  },
  cloud_error: null,
  ...overrides,
});

export const makeLink = (overrides: Partial<StudioLink> = {}): StudioLink => ({
  device: {
    device_id: "e1123c9cadb64dafd48432897072a826",
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
      models: ["qwen3:4b-instruct"],
    },
  ],
  servers: [makeServer()],
  project: makeDevice().project,
  ...overrides,
});
