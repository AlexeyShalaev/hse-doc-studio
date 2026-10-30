import type { ReactNode } from "react";
import type {
  AdminAiProvider,
  AdminBuildSettings,
  AdminInstanceSettings,
  AdminSettingState,
  AdminSigningPolicy,
} from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { AiProvidersPage } from "./AiProvidersPage";
import { BuildCard } from "./BuildCard";
import { InstanceCard } from "./InstanceCard";
import { InstancePage } from "./InstancePage";
import { Ready } from "./Ready";
import { SharedProviders } from "./SharedProviders";
import { SigningPolicyCard } from "./SigningPolicyCard";
import { SigningPolicyPage } from "./SigningPolicyPage";

const W = 640;
const noop = () => undefined;

const free: AdminSettingState = { source: "default", locked: false };
const env: AdminSettingState = { source: "env", locked: true };

const INSTANCE: AdminInstanceSettings = {
  name: "HSE Doc Studio",
  public_url: "https://studio.example.org",
  docs_url: null,
  fields: {
    "instance.name": free,
    "instance.public_url": free,
    "instance.docs_url": free,
  },
};
const INSTANCE_ENV: AdminInstanceSettings = {
  ...INSTANCE,
  docs_url: "https://docs.hse.example/studio",
  fields: { ...INSTANCE.fields, "instance.public_url": env },
};
const INSTANCE_ALL_ENV: AdminInstanceSettings = {
  ...INSTANCE_ENV,
  fields: {
    "instance.name": env,
    "instance.public_url": env,
    "instance.docs_url": env,
  },
};

const BUILD: AdminBuildSettings = {
  timeout_s: 300,
  artifact_retention_days: 30,
  fields: {
    "build.timeout_s": free,
    "build.artifact_retention_days": free,
  },
};
const BUILD_ENV: AdminBuildSettings = {
  ...BUILD,
  fields: { ...BUILD.fields, "build.timeout_s": env },
};

const POLICY_FORBIDDEN: AdminSigningPolicy = {
  server_keys: "forbidden",
  stored_keys: 0,
  fields: { "signing.server_keys": free },
};
const POLICY_BLOCKED: AdminSigningPolicy = {
  ...POLICY_FORBIDDEN,
  stored_keys: 3,
};
const POLICY_ALLOWED: AdminSigningPolicy = {
  server_keys: "allowed",
  stored_keys: 3,
  fields: { "signing.server_keys": free },
};
const POLICY_ENV: AdminSigningPolicy = {
  ...POLICY_ALLOWED,
  fields: { "signing.server_keys": env },
};

const PROVIDERS: AdminAiProvider[] = [
  {
    id: "aip_shared1",
    name: "Общий Claude",
    type: "claude",
    base_url: "",
    models: ["claude-sonnet-4-5", "claude-haiku-4-5"],
    has_api_key: true,
    created_at: "2026-10-29T10:00:00Z",
    ssl_verify: true,
    connect_timeout_s: 10,
    request_timeout_s: 60,
    shared: true,
  },
  {
    id: "aip_shared2",
    name: "Кафедральный vLLM",
    type: "openai_compat",
    base_url: "http://llm.dept.internal:8000/v1",
    models: [],
    has_api_key: false,
    created_at: "2026-10-29T10:05:00Z",
    ssl_verify: false,
    connect_timeout_s: 10,
    request_timeout_s: 120,
    shared: true,
  },
];

const entry = (
  id: string,
  title: string,
  render: () => ReactNode,
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: W,
  render: () => <Ready>{render()}</Ready>,
  ...extra,
});

const live = (scenario: string) => ({ scenario });

/** Настройки установки: название и сборка, политика ключей подписи, общие провайдеры. */
export const getAdminInstallGallery = (): GalleryGroup[] => [
  {
    id: "admin-install-instance",
    title: "Админка: название и адрес",
    entries: [
      entry("admin_instance", "Свободные поля", () => (
        <InstanceCard settings={INSTANCE} onSave={noop} />
      )),
      entry(
        "admin_instance_env",
        "Адрес задан окружением",
        () => <InstanceCard settings={INSTANCE_ENV} onSave={noop} />,
        { note: "Поле только для чтения, остальные редактируются." },
      ),
      entry("admin_instance_all_env", "Всё задано окружением", () => (
        <InstanceCard settings={INSTANCE_ALL_ENV} onSave={noop} />
      )),
      entry("admin_instance_pending", "Сохраняется", () => (
        <InstanceCard settings={INSTANCE} pending onSave={noop} />
      )),
      entry("admin_instance_failed", "Сервер отказал", () => (
        <InstanceCard
          settings={INSTANCE}
          failure={{ code: "input_invalid" }}
          onSave={noop}
        />
      )),
      entry("admin_instance_saved", "Сохранено", () => (
        <InstanceCard settings={INSTANCE} saved onSave={noop} />
      )),
    ],
  },
  {
    id: "admin-install-build",
    title: "Админка: сборка",
    entries: [
      entry("admin_build", "Значения по умолчанию", () => (
        <BuildCard settings={BUILD} onSave={noop} />
      )),
      entry("admin_build_env", "Предел задан окружением", () => (
        <BuildCard settings={BUILD_ENV} onSave={noop} />
      )),
      entry("admin_build_failed", "Сервер отказал", () => (
        <BuildCard
          settings={BUILD}
          failure={{ code: "rate_limited" }}
          onSave={noop}
        />
      )),
    ],
  },
  {
    id: "admin-install-signing",
    title: "Админка: ключи подписи",
    entries: [
      entry("admin_signing_forbidden", "Запрещено (по умолчанию)", () => (
        <SigningPolicyCard policy={POLICY_FORBIDDEN} onSave={noop} />
      )),
      entry("admin_signing_blocked", "Запрещено, ключи заблокированы", () => (
        <SigningPolicyCard policy={POLICY_BLOCKED} onSave={noop} />
      )),
      entry("admin_signing_allowed", "Разрешено", () => (
        <SigningPolicyCard policy={POLICY_ALLOWED} onSave={noop} />
      )),
      entry("admin_signing_env", "Политика задана окружением", () => (
        <SigningPolicyCard policy={POLICY_ENV} onSave={noop} />
      )),
    ],
  },
  {
    id: "admin-install-ai",
    title: "Админка: общие ИИ-провайдеры",
    entries: [
      entry("admin_ai_list", "Два провайдера: с ключом и без", () => (
        <SharedProviders
          providers={PROVIDERS}
          onAdd={noop}
          onEdit={noop}
          onDelete={noop}
        />
      )),
      entry("admin_ai_empty", "Провайдеров нет", () => (
        <SharedProviders
          providers={[]}
          onAdd={noop}
          onEdit={noop}
          onDelete={noop}
        />
      )),
    ],
  },
  {
    id: "admin-install-live",
    title: "Админка: настройки установки, живые",
    description:
      "На демо-мире. Адрес не по https (кроме localhost) отклоняется. Имя провайдера, начинающееся с limit, даёт отказ по частоте, с fail не проходит проверку моделей. Переключатель политики ключей меняет раздел «Подпись» у пользователя. Сценарии: настройки из окружения и чистая установка.",
    entries: [
      entry(
        "admin_install_page",
        "Установка",
        () => <InstancePage />,
        live("admin_ready"),
      ),
      entry(
        "admin_install_env",
        "Установка: значения из окружения",
        () => <InstancePage />,
        live("install_env_locked"),
      ),
      entry(
        "admin_install_fresh",
        "Установка: заводские значения",
        () => <InstancePage />,
        live("install_fresh"),
      ),
      entry(
        "admin_signing_page",
        "Ключи подписи",
        () => <SigningPolicyPage />,
        live("admin_ready"),
      ),
      entry(
        "admin_signing_page_env",
        "Ключи подписи: политика из окружения",
        () => <SigningPolicyPage />,
        live("install_env_locked"),
      ),
      entry(
        "admin_ai_page_empty",
        "Общие провайдеры: пусто",
        () => (
          <AiProvidersPage
            renderEditor={({ onClose }) => (
              <button type="button" className="btn xs" onClick={onClose}>
                Закрыть редактор
              </button>
            )}
          />
        ),
        live("install_fresh"),
      ),
    ],
  },
];
