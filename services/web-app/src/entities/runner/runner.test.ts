import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ZodType } from "zod";
import { z } from "zod";

import {
  CompilePlacementSchema,
  CreateMyRunnerTokenRequestSchema,
  MyRunnerRotatedSchema,
  MyRunnerSchema,
  MyRunnerTokenCreatedSchema,
  MyRunnerTokenListSchema,
  ProjectBuildRunnersSchema,
  RemoteRunnerPairRequestSchema,
  RemoteRunnerStatusSchema,
  RemoteRunnerTokenRequestSchema,
  RunnerPairingDecisionRequestSchema,
  RunnerPairingInfoSchema,
  UpdateMyRunnerRequestSchema,
  UpdateProjectBuildRunnersRequestSchema,
  UpdateRemoteRunnerRequestSchema,
} from "./model/runner.schema";
import {
  compareVersions,
  endpointSlug,
  isRunnerOutdated,
  isValidServerUrl,
  maskUserCode,
  normalizeUserCode,
} from "./lib/runnerLib";

// Эталоны раздела 10.1 спецификации personal_runners_spec.md. Пока срез C0b
// не положил их в contracts/server/fixtures, тест разбирает копии из
// спецификации; когда каталоги появятся, он разберёт и сами файлы.

const MY_RUNNER = {
  id: "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b",
  name: "MacBook Анны",
  state: "online",
  host_kind: "desktop",
  tags: ["ai", "archive:7z", "pack", "tex"],
  concurrency: 1,
  ai_concurrency: 2,
  version: "0.3.0",
  created_at: "2026-10-30T08:00:00Z",
  last_seen_at: "2026-10-30T09:44:50Z",
  last_seen_ip: "203.0.113.7",
  paused: false,
  paused_by: null,
  revoked: false,
  running_jobs: 1,
  ai_endpoints: [{ name: "ollama", flavor: "ollama" }],
  features: ["ai_relay", "ai_slots", "announce", "offline"],
};
const OFFLINE_CLI = {
  ...MY_RUNNER,
  state: "offline",
  host_kind: "cli",
  ai_endpoints: [],
  features: [],
  last_seen_ip: null,
  running_jobs: 0,
};
const TOKEN = {
  id: "8a7b6c5d4e3f40112233445566778899",
  label: "Домашний сервер",
  created_at: "2026-10-30T08:00:00Z",
  expires_at: "2026-10-31T08:00:00Z",
  used: false,
  revoked: false,
};
const BUILD_RUNNERS = {
  policy: "shared",
  editable: true,
  project_kind: "personal",
  personal_runners_enabled: true,
  my_builds: "personal_first",
  wait_s: 5,
  owner_runners: [{ name: "MacBook Анны", state: "online" }],
};
const REMOTE = {
  enabled: true,
  server_url: "https://studio.example.org",
  paired: true,
  runner_id: "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b",
  runner_name: "MacBook Анны",
  state: "online",
  detail_code: null,
  running_jobs: 0,
  concurrency: 1,
  yield_to_local: true,
  docker: "ok",
  tex_image: "ready",
  ai_endpoints: [
    {
      name: "ollama",
      provider_id: "6a5b4c3d-2e1f-4a0b-9c8d-7e6f5a4b3c2d",
      flavor: "ollama",
      url: "http://localhost:11434/v1",
      announced: false,
    },
  ],
  pairing: null,
};

const SAMPLES: [string, ZodType, unknown][] = [
  ["MyRunner/online_desktop", MyRunnerSchema, MY_RUNNER],
  ["MyRunner/offline_cli", MyRunnerSchema, OFFLINE_CLI],
  ["MyRunner/disabled", MyRunnerSchema, { ...MY_RUNNER, state: "disabled" }],
  [
    "MyRunner/revoked",
    MyRunnerSchema,
    { ...MY_RUNNER, state: "revoked", revoked: true },
  ],
  ["MyRunnerTokenList/one", MyRunnerTokenListSchema, [TOKEN]],
  [
    "CreateMyRunnerTokenRequest/default",
    CreateMyRunnerTokenRequestSchema,
    { label: "Домашний сервер", ttl_hours: 24 },
  ],
  [
    "MyRunnerTokenCreated/default",
    MyRunnerTokenCreatedSchema,
    {
      token: TOKEN,
      secret: "hsrt_Q2xvdWRSdW5uZXJUb2tlbkV4YW1wbGUx",
      command: "HSE_RUNNER__TOKEN=hsrt_x hse-doc-studio runner",
      docker_command: "docker run -d hse-doc-studio runner",
    },
  ],
  [
    "UpdateMyRunnerRequest/rename",
    UpdateMyRunnerRequestSchema,
    { name: "Рабочий ПК", paused: null },
  ],
  [
    "UpdateMyRunnerRequest/pause",
    UpdateMyRunnerRequestSchema,
    { name: null, paused: true },
  ],
  [
    "MyRunnerRotated/default",
    MyRunnerRotatedSchema,
    {
      runner: OFFLINE_CLI,
      runner_token: "hsrn_Um90YXRlZFJ1bm5lclRva2VuRXhhbXBsZTI",
      command: "HSE_RUNNER__RUNNER_TOKEN=hsrn_x hse-doc-studio runner",
    },
  ],
  [
    "RunnerPairingInfo/pending",
    RunnerPairingInfoSchema,
    {
      user_code: "BCDF-2345",
      name: "MacBook Анны",
      host_kind: "desktop",
      requested_at: "2026-10-30T09:40:00Z",
      expires_at: "2026-10-30T09:50:00Z",
      client_ip: "203.0.113.7",
      status: "pending",
    },
  ],
  [
    "RunnerPairingDecisionRequest/approve",
    RunnerPairingDecisionRequestSchema,
    { decision: "approve" },
  ],
  [
    "ProjectBuildRunners/owner_shared",
    ProjectBuildRunnersSchema,
    BUILD_RUNNERS,
  ],
  [
    "ProjectBuildRunners/org_project",
    ProjectBuildRunnersSchema,
    {
      ...BUILD_RUNNERS,
      project_kind: "org",
      editable: false,
      owner_runners: [],
      my_builds: "shared",
    },
  ],
  [
    "UpdateProjectBuildRunnersRequest/owner",
    UpdateProjectBuildRunnersRequestSchema,
    { policy: "owner" },
  ],
  [
    "CompilePlacement/personal_me",
    CompilePlacementSchema,
    {
      state: "personal",
      runner_name: "MacBook Анны",
      runner_owner: "me",
      fallback: null,
      wait_s: null,
    },
  ],
  [
    "CompilePlacement/shared_timeout",
    CompilePlacementSchema,
    {
      state: "shared",
      runner_name: null,
      runner_owner: null,
      fallback: "timeout",
      wait_s: 5,
    },
  ],
  ["RemoteRunnerStatus/online", RemoteRunnerStatusSchema, REMOTE],
  [
    "RemoteRunnerStatus/pairing",
    RemoteRunnerStatusSchema,
    {
      ...REMOTE,
      state: "pairing",
      pairing: {
        user_code: "BCDF-2345",
        verification_uri_complete:
          "https://studio.example.org/settings/runners/pair?code=BCDF-2345",
        expires_at: "2026-10-30T09:50:00Z",
      },
    },
  ],
  [
    "UpdateRemoteRunnerRequest/enable",
    UpdateRemoteRunnerRequestSchema,
    {
      enabled: true,
      server_url: null,
      name: null,
      concurrency: null,
      yield_to_local: null,
      ai_endpoints: null,
    },
  ],
  [
    "RemoteRunnerPairRequest/default",
    RemoteRunnerPairRequestSchema,
    { server_url: "https://studio.example.org", name: "MacBook Анны" },
  ],
  [
    "RemoteRunnerTokenRequest/default",
    RemoteRunnerTokenRequestSchema,
    { server_url: "https://studio.example.org", token: "hsrt_x" },
  ],
];

describe("личные раннеры: схемы по эталонам спецификации", () => {
  it.each(SAMPLES)("%s разбирается без потерь", (_name, schema, body) => {
    const parsed = schema.safeParse(body);
    expect(parsed.success).toBe(true);
    expect(parsed.data).toEqual(body);
  });

  it.each(SAMPLES.filter(([, , body]) => !Array.isArray(body)))(
    "%s: лишнее поле отвергается",
    (_name, schema, body) => {
      expect(
        schema.safeParse({ ...(body as object), surprise: 1 }).success,
      ).toBe(false);
    },
  );

  it("соавтор видит у раннера владельца только имя и состояние", () => {
    expect(
      ProjectBuildRunnersSchema.safeParse({
        ...BUILD_RUNNERS,
        owner_runners: [{ name: "X", state: "online", id: "r1" }],
      }).success,
    ).toBe(false);
  });
});

// Когда эталоны появятся в contracts/server/fixtures, они обязаны проходить те же схемы.
const FIXTURES = join(
  import.meta.dirname,
  ...Array<string>(5).fill(".."),
  "contracts",
  "server",
  "fixtures",
);
const BY_DIR: Record<string, ZodType> = {
  MyRunner: MyRunnerSchema,
  MyRunnerList: z.array(MyRunnerSchema),
  MyRunnerTokenList: MyRunnerTokenListSchema,
  CreateMyRunnerTokenRequest: CreateMyRunnerTokenRequestSchema,
  MyRunnerTokenCreated: MyRunnerTokenCreatedSchema,
  UpdateMyRunnerRequest: UpdateMyRunnerRequestSchema,
  MyRunnerRotated: MyRunnerRotatedSchema,
  RunnerPairingInfo: RunnerPairingInfoSchema,
  RunnerPairingDecisionRequest: RunnerPairingDecisionRequestSchema,
  ProjectBuildRunners: ProjectBuildRunnersSchema,
  UpdateProjectBuildRunnersRequest: UpdateProjectBuildRunnersRequestSchema,
  CompilePlacement: CompilePlacementSchema,
  RemoteRunnerStatus: RemoteRunnerStatusSchema,
  UpdateRemoteRunnerRequest: UpdateRemoteRunnerRequestSchema,
  RemoteRunnerPairRequest: RemoteRunnerPairRequestSchema,
  RemoteRunnerTokenRequest: RemoteRunnerTokenRequestSchema,
};
const contractFiles = Object.entries(BY_DIR).flatMap(([dir, schema]) => {
  const path = join(FIXTURES, dir);
  if (!existsSync(path)) return [];
  return readdirSync(path)
    .filter((f) => f.endsWith(".json"))
    .map(
      (f) =>
        [
          `${dir}/${f}`,
          schema,
          JSON.parse(readFileSync(join(path, f), "utf8")) as unknown,
        ] as const,
    );
});

describe("личные раннеры: эталоны contracts/server, если они уже есть", () => {
  it("каталоги эталонов либо ещё не положены, либо не пусты", () => {
    expect(contractFiles.every(([, , body]) => body !== null)).toBe(true);
  });

  it.each(contractFiles)("%s разбирается без потерь", (_name, schema, body) => {
    const parsed = schema.safeParse(body);
    expect(parsed.success).toBe(true);
    expect(parsed.data).toEqual(body);
  });
});

describe("личные раннеры: помощники", () => {
  it("код сопряжения нормализуется без учёта регистра и дефиса", () => {
    expect(normalizeUserCode("bcdf2345")).toBe("BCDF-2345");
    expect(normalizeUserCode(" bcdf-2345 ")).toBe("BCDF-2345");
    // Похожих на цифры букв (O, I, A, E) в алфавите нет.
    expect(normalizeUserCode("ABCD-2345")).toBeNull();
    expect(normalizeUserCode("BCDF-234")).toBeNull();
  });

  it("маска вводит дефис после четвёртого знака", () => {
    expect(maskUserCode("bcd")).toBe("BCD");
    expect(maskUserCode("bcdf23")).toBe("BCDF-23");
    expect(maskUserCode("bcdf-2345-99")).toBe("BCDF-2345");
  });

  it("версии сравниваются по числам", () => {
    expect(compareVersions("0.10.0", "0.9.9")).toBeGreaterThan(0);
    expect(isRunnerOutdated("0.1.4", "0.2.0")).toBe(true);
    expect(isRunnerOutdated("0.2.0", "0.2.0")).toBe(false);
    expect(isRunnerOutdated("0.1.0", "")).toBe(false);
  });

  it("адрес сервера: https, а http только для localhost", () => {
    expect(isValidServerUrl("https://studio.example.org")).toBe(true);
    expect(isValidServerUrl("http://localhost:8000")).toBe(true);
    expect(isValidServerUrl("http://studio.example.org")).toBe(false);
    expect(isValidServerUrl("studio")).toBe(false);
  });

  it("имя ИИ-адреса из имени провайдера", () => {
    expect(endpointSlug("LM Studio")).toBe("lm-studio");
    expect(endpointSlug("Ollama")).toBe("ollama");
    expect(endpointSlug("Модель")).toBe("model");
  });
});
