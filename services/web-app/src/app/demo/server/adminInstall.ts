import type {
  AdminBuildSettings,
  AdminInstanceSettings,
  AdminSettingState,
  AdminSigningPolicy,
} from "@entities/session";

// Настройки установки в демо-мире админки: название и адрес, сборка, политика ключей подписи
// и общие ИИ-провайдеры. Формы совпадают с contracts/server/fixtures (AdminInstanceSettings...).

/** Общий провайдер в форме ответа сервера: ключ только признаком key_set. */
export type DemoSharedProvider = {
  id: string;
  name: string;
  type: "claude" | "openai" | "openai_compat" | "ollama";
  base_url: string;
  models: string[];
  key_set: boolean;
  ssl_verify: boolean;
  connect_timeout_s: number;
  request_timeout_s: number;
  created_at: string;
};

export type DemoAdminInstall = {
  instance: AdminInstanceSettings;
  build: AdminBuildSettings;
  signing: AdminSigningPolicy;
  providers: DemoSharedProvider[];
};

/**
 * default: всё редактируется, хранение ключей разрешено и два ключа уже лежат на сервере;
 * env_locked: адрес и предел сборки заданы окружением, ключи заблокированы запретом;
 * fresh: заводские значения, хранение ключей запрещено, общих провайдеров нет.
 */
export type ServerDemoInstallSeed = "default" | "env_locked" | "fresh";

const state = (
  source: AdminSettingState["source"] = "default",
): AdminSettingState => ({ source, locked: source === "env" });

const NOW = "2026-10-29T10:00:00Z";

const providers = (): DemoSharedProvider[] => [
  {
    id: "aip_shared1",
    name: "Общий Claude",
    type: "claude",
    base_url: "",
    models: ["claude-sonnet-4-5", "claude-haiku-4-5"],
    key_set: true,
    created_at: NOW,
    ssl_verify: true,
    connect_timeout_s: 10,
    request_timeout_s: 60,
  },
  {
    id: "aip_shared2",
    name: "Кафедральный vLLM",
    type: "openai_compat",
    base_url: "http://llm.dept.internal:8000/v1",
    models: [],
    key_set: false,
    created_at: NOW,
    ssl_verify: false,
    connect_timeout_s: 10,
    request_timeout_s: 120,
  },
];

export const createDemoAdminInstall = (
  seed: ServerDemoInstallSeed = "default",
): DemoAdminInstall => {
  if (seed === "env_locked") {
    return {
      instance: {
        name: "Studio ВШЭ",
        public_url: "https://studio.hse.example",
        docs_url: "https://docs.hse.example/studio",
        fields: {
          "instance.name": state("admin"),
          "instance.public_url": state("env"),
          "instance.docs_url": state("admin"),
        },
      },
      build: {
        timeout_s: 900,
        artifact_retention_days: 14,
        fields: {
          "build.timeout_s": state("env"),
          "build.artifact_retention_days": state("admin"),
        },
      },
      signing: {
        server_keys: "forbidden",
        stored_keys: 2,
      },
      providers: providers().slice(0, 1),
    };
  }
  if (seed === "fresh") {
    return {
      instance: {
        name: "HSE Doc Studio",
        public_url: "http://localhost:8080",
        docs_url: null,
        fields: {
          "instance.name": state(),
          "instance.public_url": state(),
          "instance.docs_url": state(),
        },
      },
      build: {
        timeout_s: 300,
        artifact_retention_days: 30,
        fields: {
          "build.timeout_s": state(),
          "build.artifact_retention_days": state(),
        },
      },
      signing: {
        server_keys: "forbidden",
        stored_keys: 0,
      },
      providers: [],
    };
  }
  return {
    instance: {
      name: "HSE Doc Studio",
      public_url: "https://studio.example.org",
      docs_url: null,
      fields: {
        "instance.name": state(),
        "instance.public_url": state("admin"),
        "instance.docs_url": state(),
      },
    },
    build: {
      timeout_s: 300,
      artifact_retention_days: 30,
      fields: {
        "build.timeout_s": state(),
        "build.artifact_retention_days": state("admin"),
      },
    },
    signing: {
      server_keys: "allowed",
      stored_keys: 2,
    },
    providers: providers(),
  };
};
