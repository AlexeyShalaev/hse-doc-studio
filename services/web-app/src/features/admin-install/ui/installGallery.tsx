import type { ReactNode } from "react";
import { ApiError } from "@shared/api";
import type {
  AdminBuildSettings,
  AdminInstanceSettings,
  AdminSettingState,
  AdminSigningPolicy,
} from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import type { AIProvider } from "@entities/ai-provider";
import { AiProvidersPage } from "./AiProvidersPage";
import { InstanceForm } from "./InstanceForm";
import { InstancePage } from "./InstancePage";
import { Ready } from "./Ready";
import { SharedProviders } from "./SharedProviders";
import { SigningPolicyForm } from "./SigningPolicyForm";
import { SigningPolicyPage } from "./SigningPolicyPage";

const W = 640;
const noop = () => undefined;
const ok = () => Promise.resolve();
// Отказ сервера в галерее: тот же ApiError, что приходит от клиента.
const refuse = (code: string) => () =>
  Promise.reject(new ApiError(code, code, 429));
const pending = () => new Promise<never>(noop);

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
// Сервер с личными раннерами: три поля и ключи runners.* в fields.
const BUILD_PERSONAL: AdminBuildSettings = {
  ...BUILD,
  personal_runners_enabled: true,
  personal_runner_wait_s: 5,
  personal_runners_max_per_user: 5,
  fields: {
    ...BUILD.fields,
    "runners.personal_enabled": free,
    "runners.personal_wait_s": free,
    "runners.personal_max_per_user": free,
  },
};
const BUILD_PERSONAL_ENV: AdminBuildSettings = {
  ...BUILD_PERSONAL,
  personal_runners_enabled: false,
  fields: { ...BUILD_PERSONAL.fields, "runners.personal_enabled": env },
};
const BUILD_ENV: AdminBuildSettings = {
  ...BUILD,
  fields: { ...BUILD.fields, "build.timeout_s": env },
};

const BUILD_ALL_ENV: AdminBuildSettings = {
  ...BUILD,
  fields: {
    "build.timeout_s": env,
    "build.artifact_retention_days": env,
  },
};

const POLICY_FORBIDDEN: AdminSigningPolicy = {
  server_keys: "forbidden",
  stored_keys: 0,
};
const POLICY_BLOCKED: AdminSigningPolicy = {
  ...POLICY_FORBIDDEN,
  stored_keys: 3,
};
const POLICY_ALLOWED: AdminSigningPolicy = {
  server_keys: "allowed",
  stored_keys: 3,
};

const PROVIDERS: AIProvider[] = [
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
    title: "Админка: установка",
    description:
      "Поменяйте любое поле: внизу появится панель сохранения со счётчиком правок.",
    entries: [
      entry("admin_instance", "Свободные поля", () => (
        <InstanceForm
          instance={INSTANCE}
          build={BUILD}
          saveInstance={ok}
          saveBuild={ok}
        />
      )),
      entry(
        "admin_instance_env",
        "Адрес и предел сборки заданы окружением",
        () => (
          <InstanceForm
            instance={INSTANCE_ENV}
            build={BUILD_ENV}
            saveInstance={ok}
            saveBuild={ok}
          />
        ),
        {
          note: "Закрытые поля с замком и подсказкой, остальные редактируются.",
        },
      ),
      entry("admin_instance_all_env", "Всё задано окружением", () => (
        <InstanceForm
          instance={INSTANCE_ALL_ENV}
          build={BUILD_ALL_ENV}
          saveInstance={ok}
          saveBuild={ok}
        />
      )),
      entry(
        "admin_instance_personal",
        "Личные раннеры: разрешены",
        () => (
          <InstanceForm
            instance={INSTANCE}
            build={BUILD_PERSONAL}
            saveInstance={ok}
            saveBuild={ok}
          />
        ),
        {
          note: "Выключите переключатель и сохраните: появится подтверждение.",
        },
      ),
      entry(
        "admin_instance_personal_env",
        "Личные раннеры выключены окружением",
        () => (
          <InstanceForm
            instance={INSTANCE}
            build={BUILD_PERSONAL_ENV}
            saveInstance={ok}
            saveBuild={ok}
          />
        ),
      ),
      entry(
        "admin_instance_pending",
        "Сохранение не отвечает",
        () => (
          <InstanceForm
            instance={INSTANCE}
            build={BUILD}
            saveInstance={pending}
            saveBuild={pending}
          />
        ),
        { note: "Поменяйте поле и нажмите «Сохранить»." },
      ),
      entry(
        "admin_instance_failed",
        "Сервер отказал",
        () => (
          <InstanceForm
            instance={INSTANCE}
            build={BUILD}
            saveInstance={refuse("rate_limited")}
            saveBuild={refuse("rate_limited")}
          />
        ),
        { note: "Поменяйте поле и нажмите «Сохранить»: ошибка в панели." },
      ),
    ],
  },
  {
    id: "admin-install-signing",
    title: "Админка: ключи подписи",
    entries: [
      entry("admin_signing_forbidden", "Запрещено (по умолчанию)", () => (
        <SigningPolicyForm policy={POLICY_FORBIDDEN} onSave={ok} />
      )),
      entry("admin_signing_blocked", "Запрещено, ключи заблокированы", () => (
        <SigningPolicyForm policy={POLICY_BLOCKED} onSave={ok} />
      )),
      entry("admin_signing_allowed", "Разрешено", () => (
        <SigningPolicyForm policy={POLICY_ALLOWED} onSave={ok} />
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
          onCheck={(p) =>
            p.has_api_key
              ? Promise.resolve({ models: p.models })
              : Promise.reject(new Error("ConnectError"))
          }
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
