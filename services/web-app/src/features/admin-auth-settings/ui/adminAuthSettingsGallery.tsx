import { useEffect, useState, type ReactNode } from "react";
import type {
  AdminAuthSettings as AuthSettings,
  AdminOidcProvider,
  AdminRegistrationSettings,
  AdminSettingState,
  AdminSmtpSettings,
} from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { ensureAdminSettingsLocales } from "../lib/locales";
import { AdminAuthSettings } from "./AdminAuthSettings";
import { OidcCard } from "./OidcCard";
import { RegistrationCard } from "./RegistrationCard";
import { SignInMethodsCard } from "./SignInMethodsCard";
import { SmtpCard } from "./SmtpCard";

const W = 640;
const noop = () => undefined;

/** Словарь настроек грузится вместе с чанком админки; галерея ждёт его сама. */
const Ready = ({ children }: { children: ReactNode }) => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    void ensureAdminSettingsLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);
  return ready ? <>{children}</> : null;
};

const free: AdminSettingState = { source: "default", locked: false };
const env: AdminSettingState = { source: "env", locked: true };

const REGISTRATION: AdminRegistrationSettings = {
  registration_mode: "invite",
  registration_domains: [],
  require_approval: false,
  fields: {
    "auth.registration_mode": free,
    "auth.registration_domains": free,
    "auth.require_approval": free,
  },
};
const DOMAINS: AdminRegistrationSettings = {
  ...REGISTRATION,
  registration_mode: "domains",
  registration_domains: ["edu.hse.ru", "hse.ru"],
  require_approval: true,
};
const REG_ENV: AdminRegistrationSettings = {
  ...DOMAINS,
  fields: {
    "auth.registration_mode": env,
    "auth.registration_domains": { source: "admin", locked: false },
    "auth.require_approval": env,
  },
};
const REG_ALL_ENV: AdminRegistrationSettings = {
  ...DOMAINS,
  fields: {
    "auth.registration_mode": env,
    "auth.registration_domains": env,
    "auth.require_approval": env,
  },
};

const AUTH: AuthSettings = {
  password_enabled: true,
  oidc_enabled_count: 0,
  fields: { "auth.password_enabled": free },
};

const SMTP_KEYS = [
  "host",
  "port",
  "security",
  "username",
  "password",
  "from_address",
  "from_name",
];
const smtpFields = (state: AdminSettingState) =>
  Object.fromEntries(SMTP_KEYS.map((k) => [`smtp.${k}`, state]));

const SMTP_ON: AdminSmtpSettings = {
  enabled: true,
  host: "smtp.example.org",
  port: 587,
  security: "starttls",
  username: "mailer",
  password_set: true,
  from_address: "studio@example.org",
  from_name: "Studio",
  fields: smtpFields({ source: "admin", locked: false }),
};
const SMTP_OFF: AdminSmtpSettings = {
  enabled: false,
  host: null,
  port: 587,
  security: "starttls",
  username: null,
  password_set: false,
  from_address: "no-reply@localhost",
  from_name: "HSE Doc Studio",
  fields: smtpFields(free),
};
const SMTP_ENV: AdminSmtpSettings = {
  ...SMTP_ON,
  port: 465,
  security: "tls",
  fields: smtpFields(env),
};

const PROVIDERS: AdminOidcProvider[] = [
  {
    id: "3f2b9c1e7a4d4b6f8e0a1c2d3e4f5a6b",
    label: "HSE ID",
    issuer: "https://id.example.org",
    client_id: "studio",
    client_secret_set: true,
    scopes: "openid email profile",
    enabled: true,
    auto_provision: false,
    created_at: "2026-10-29T10:00:00Z",
  },
  {
    id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    label: "Google",
    issuer: "https://accounts.google.com",
    client_id: "studio",
    client_secret_set: true,
    scopes: "openid email profile",
    enabled: false,
    auto_provision: true,
    created_at: "2026-10-29T10:00:00Z",
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

const registration = (
  settings: AdminRegistrationSettings,
  extra: Partial<Parameters<typeof RegistrationCard>[0]> = {},
) => (
  <RegistrationCard settings={settings} smtpEnabled onSave={noop} {...extra} />
);

const signin = (
  settings: AuthSettings,
  extra: Partial<Parameters<typeof SignInMethodsCard>[0]> = {},
) => <SignInMethodsCard settings={settings} onSave={noop} {...extra} />;

const oidc = (extra: Partial<Parameters<typeof OidcCard>[0]> = {}) => (
  <OidcCard
    status="ready"
    providers={PROVIDERS}
    baseUrl="https://studio.example.org"
    onCreate={noop}
    onUpdate={noop}
    onToggle={noop}
    onDelete={noop}
    {...extra}
  />
);

const smtp = (
  settings: AdminSmtpSettings,
  extra: Partial<Parameters<typeof SmtpCard>[0]> = {},
) => (
  <SmtpCard
    settings={settings}
    onSave={noop}
    test={{ onSend: noop, defaultTo: "ivan.sidorov@example.org" }}
    {...extra}
  />
);

/** Настройки входа в админке: каждая карточка в своих состояниях и живой раздел на демо-мире. */
export const getAdminAuthSettingsGallery = (): GalleryGroup[] => [
  {
    id: "admin-registration",
    title: "Админка: регистрация",
    entries: [
      entry("admin_reg_invite", "По приглашению", () =>
        registration(REGISTRATION),
      ),
      entry("admin_reg_domains", "Для доменов, с одобрением", () =>
        registration(DOMAINS),
      ),
      entry(
        "admin_reg_domains_nosmtp",
        "Домены без почты",
        () => registration(DOMAINS, { smtpEnabled: false }),
        { note: "Предупреждение: аккаунты будут ждать одобрения." },
      ),
      entry(
        "admin_reg_open",
        "Открытая без одобрения",
        () =>
          registration({
            ...REGISTRATION,
            registration_mode: "open",
          }),
        { note: "Предупреждение об открытой регистрации." },
      ),
      entry("admin_reg_closed", "Закрытая", () =>
        registration({ ...REGISTRATION, registration_mode: "closed" }),
      ),
      entry(
        "admin_reg_env",
        "Режим и одобрение заданы окружением",
        () => registration(REG_ENV),
        { note: "Домены ещё можно править, остальное только читается." },
      ),
      entry(
        "admin_reg_all_env",
        "Всё задано окружением",
        () => registration(REG_ALL_ENV),
        { note: "Кнопки «Сохранить» нет, вместо неё пояснение." },
      ),
      entry("admin_reg_saving", "Сохраняется", () =>
        registration(DOMAINS, { pending: true }),
      ),
      entry("admin_reg_saved", "Сохранено", () =>
        registration(DOMAINS, { saved: true }),
      ),
      entry("admin_reg_failed", "Сохранить не вышло", () =>
        registration(DOMAINS, { failure: { code: "network" } }),
      ),
    ],
  },
  {
    id: "admin-signin",
    title: "Админка: способы входа",
    entries: [
      entry(
        "admin_signin_only",
        "Единственный способ входа",
        () => signin(AUTH),
        { note: "Пароль отключить нельзя, пока нет провайдера." },
      ),
      entry("admin_signin_sso", "Пароль и два провайдера", () =>
        signin({ ...AUTH, oidc_enabled_count: 2 }),
      ),
      entry("admin_signin_off", "Пароль выключен", () =>
        signin({ ...AUTH, password_enabled: false, oidc_enabled_count: 1 }),
      ),
      entry("admin_signin_locked", "Задано окружением", () =>
        signin({
          ...AUTH,
          oidc_enabled_count: 1,
          fields: { "auth.password_enabled": env },
        }),
      ),
      entry("admin_signin_last", "Отказ: последний способ входа", () =>
        signin(
          { ...AUTH, oidc_enabled_count: 1 },
          { failure: { code: "last_login_method" } },
        ),
      ),
      entry("admin_signin_saving", "Сохраняется", () =>
        signin({ ...AUTH, oidc_enabled_count: 1 }, { pending: true }),
      ),
    ],
  },
  {
    id: "admin-oidc",
    title: "Админка: единый вход",
    entries: [
      entry("admin_oidc_list", "Два провайдера", () => oidc()),
      entry("admin_oidc_empty", "Провайдеров нет", () =>
        oidc({ providers: [] }),
      ),
      entry("admin_oidc_loading", "Загрузка", () =>
        oidc({ status: "loading", providers: [] }),
      ),
      entry("admin_oidc_error", "Не загрузились", () =>
        oidc({ status: "error", providers: [], onRetry: noop }),
      ),
      entry("admin_oidc_failed", "Отказ: последний способ входа", () =>
        oidc({ failure: { code: "last_login_method" } }),
      ),
    ],
  },
  {
    id: "admin-smtp",
    title: "Админка: почта",
    entries: [
      entry("admin_smtp_on", "Почта настроена, пароль задан", () =>
        smtp(SMTP_ON),
      ),
      entry("admin_smtp_off", "Почта не настроена", () => smtp(SMTP_OFF)),
      entry("admin_smtp_env", "Всё задано окружением", () => smtp(SMTP_ENV), {
        note: "Поля только читаются, пароль не показывается.",
      }),
      entry("admin_smtp_saving", "Сохраняется", () =>
        smtp(SMTP_ON, { pending: true }),
      ),
      entry("admin_smtp_failed", "Сохранить не вышло", () =>
        smtp(SMTP_ON, { failure: { code: "network" } }),
      ),
      entry("admin_smtp_test_pending", "Тест идёт", () =>
        smtp(SMTP_ON, { test: { pending: true, onSend: noop } }),
      ),
      entry("admin_smtp_test_ok", "Тестовое письмо ушло", () =>
        smtp(SMTP_ON, {
          test: { result: { ok: true, error: null }, onSend: noop },
        }),
      ),
      entry("admin_smtp_test_failed", "Тестовое письмо не ушло", () =>
        smtp(SMTP_ON, {
          test: {
            result: {
              ok: false,
              error: "SMTPConnectError: connection refused",
            },
            onSend: noop,
          },
        }),
      ),
    ],
  },
  {
    id: "admin-settings-live",
    title: "Админка: настройки входа, живой раздел",
    description:
      "На демо-мире. Почта: сервер с fail в имени даёт отказ теста. Нельзя выключить пароль без включённых провайдеров. Секреты после сохранения не показываются.",
    entries: [
      entry(
        "admin_settings_live",
        "Администратор",
        () => <AdminAuthSettings />,
        { scenario: "admin_ready" },
      ),
      entry(
        "admin_settings_live_env",
        "Часть настроек от окружения",
        () => <AdminAuthSettings />,
        { scenario: "admin_env_locked" },
      ),
      entry(
        "admin_settings_live_sso",
        "Только единый вход, почты нет",
        () => <AdminAuthSettings />,
        { scenario: "admin_sso" },
      ),
    ],
  },
];
