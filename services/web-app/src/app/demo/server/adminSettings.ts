import type {
  AdminAuthSettings,
  AdminOidcProvider,
  AdminRegistrationSettings,
  AdminSettingState,
  AdminSmtpSettings,
} from "@entities/session";
import type { ServerDemoAdminSeed } from "./scenarios";

// Настройки входа в демо-мире админки: регистрация, пароль, почта и провайдеры.
// Формы совпадают с contracts/server/fixtures (AdminRegistrationSettings...).

export type DemoAdminSettings = {
  registration: AdminRegistrationSettings;
  /** Пароль и число включённых провайдеров считаются из providers. */
  auth: Pick<AdminAuthSettings, "password_enabled" | "fields">;
  smtp: AdminSmtpSettings;
  providers: AdminOidcProvider[];
};

const field = (
  source: AdminSettingState["source"] = "default",
): AdminSettingState => ({ source, locked: source === "env" });

const SMTP_KEYS = [
  "host",
  "port",
  "security",
  "username",
  "password",
  "from_address",
  "from_name",
] as const;

const smtpFields = (
  source: AdminSettingState["source"],
): Record<string, AdminSettingState> =>
  Object.fromEntries(SMTP_KEYS.map((k) => [`smtp.${k}`, field(source)]));

const NOW = "2026-10-29T10:00:00Z";

const PROVIDERS: AdminOidcProvider[] = [
  {
    id: "keycloak",
    label: "HSE SSO",
    issuer: "https://id.example.org",
    client_id: "studio",
    client_secret_set: true,
    scopes: "openid email profile",
    enabled: true,
    auto_provision: false,
    created_at: NOW,
  },
  {
    id: "google",
    label: "Google",
    issuer: "https://accounts.google.com",
    client_id: "studio",
    client_secret_set: true,
    scopes: "openid email profile",
    enabled: true,
    auto_provision: true,
    created_at: NOW,
  },
];

export const createDemoAdminSettings = (
  seed: ServerDemoAdminSeed = "default",
): DemoAdminSettings => {
  if (seed === "env_locked") {
    return {
      registration: {
        registration_mode: "domains",
        registration_domains: ["edu.hse.ru", "hse.ru"],
        require_approval: true,
        fields: {
          "auth.registration_mode": field("env"),
          "auth.registration_domains": field("admin"),
          "auth.require_approval": field("env"),
        },
      },
      auth: {
        password_enabled: true,
        fields: { "auth.password_enabled": field() },
      },
      smtp: {
        enabled: true,
        host: "smtp.example.org",
        port: 465,
        security: "tls",
        username: "mailer",
        password_set: true,
        from_address: "studio@example.org",
        from_name: "Studio",
        fields: smtpFields("env"),
      },
      providers: [],
    };
  }
  if (seed === "sso") {
    return {
      registration: {
        registration_mode: "closed",
        registration_domains: [],
        require_approval: false,
        fields: {
          "auth.registration_mode": field("admin"),
          "auth.registration_domains": field(),
          "auth.require_approval": field(),
        },
      },
      auth: {
        password_enabled: false,
        fields: { "auth.password_enabled": field("admin") },
      },
      smtp: {
        enabled: false,
        host: null,
        port: 587,
        security: "starttls",
        username: null,
        password_set: false,
        from_address: "no-reply@localhost",
        from_name: "HSE Doc Studio",
        fields: smtpFields("default"),
      },
      providers: PROVIDERS.map((p) => ({ ...p })),
    };
  }
  return {
    registration: {
      registration_mode: "invite",
      registration_domains: [],
      require_approval: false,
      fields: {
        "auth.registration_mode": field(),
        "auth.registration_domains": field(),
        "auth.require_approval": field(),
      },
    },
    auth: {
      password_enabled: true,
      fields: { "auth.password_enabled": field() },
    },
    smtp: {
      enabled: true,
      host: "smtp.example.org",
      port: 587,
      security: "starttls",
      username: "mailer",
      password_set: true,
      from_address: "studio@example.org",
      from_name: "Studio",
      fields: smtpFields("admin"),
    },
    providers: PROVIDERS.slice(0, 1).map((p) => ({ ...p })),
  };
};
