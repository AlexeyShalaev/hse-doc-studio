import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type {
  AdminAuthSettings,
  AdminOidcProvider,
  AdminSettingState,
  RegistrationMode,
} from "@entities/session";
import { createInstallRoutes } from "./installRoutes";
import { createOpsRoutes } from "./opsRoutes";
import { createOrgRoutes } from "./orgRoutes";
import { createPeopleRoutes } from "./peopleRoutes";
import { adminSettingsOf, type ServerDemoWorld } from "./world";

// Демо админки: настройки входа (регистрация, пароль, почта, провайдеры OIDC).
// Маршруты живут на клиенте /api/admin. Тела совпадают с contracts/server/fixtures.
//
// Особые значения, чтобы вызывать каждое состояние руками:
//  - почта: сервер с fail в имени или получатель fail@... дают отказ тестового письма;
//  - выключить пароль без включённых провайдеров: last_login_method;
//  - значения, заданные окружением (сценарий admin_env_locked), не меняются: setting_locked;
//  - издатель провайдера не https и не localhost: 422 input_invalid.

const MODES: readonly RegistrationMode[] = [
  "invite",
  "domains",
  "open",
  "closed",
];

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const locked = () =>
  demoError(409, "setting_locked", "The value is set by the environment");
const lastMethod = () =>
  demoError(
    409,
    "last_login_method",
    "The last sign-in method cannot be removed",
  );
const invalid = () => demoError(422, "input_invalid", "Invalid input");

const admin = (source: AdminSettingState["source"]): AdminSettingState => ({
  source,
  locked: false,
});

export const createAdminRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  /** Не вошёл: 401. Не админ: 404, как у настоящего /api/admin. */
  const guard = (): DemoResponse | null => {
    const { user } = getWorld().bootstrap;
    if (user === null)
      return demoError(401, "auth_required", "Authentication required");
    return user.is_instance_admin
      ? null
      : demoError(404, "not_found", "Not Found");
  };
  const guarded =
    (handler: DemoRoute["handler"]): DemoRoute["handler"] =>
    (req) =>
      guard() ?? handler(req);

  const state = () => adminSettingsOf(getWorld());
  const enabledCount = () => state().providers.filter((p) => p.enabled).length;

  /** Экран входа читает настройки из bootstrap: держим его в согласии с админкой. */
  const syncBootstrap = () => {
    const world = getWorld();
    const s = state();
    world.bootstrap = {
      ...world.bootstrap,
      auth: {
        ...world.bootstrap.auth,
        registration_mode: s.registration.registration_mode,
        password_enabled: s.auth.password_enabled,
        smtp_enabled: s.smtp.enabled,
        oidc_providers: s.providers
          .filter((p) => p.enabled)
          .map((p) => ({ id: p.id, label: p.label })),
      },
    };
  };

  const authView = (): AdminAuthSettings => ({
    ...state().auth,
    oidc_enabled_count: enabledCount(),
  });

  const providerFrom = (
    body: Record<string, unknown>,
    base: AdminOidcProvider,
  ): AdminOidcProvider | null => {
    const next = { ...base };
    if (typeof body.label === "string") next.label = body.label.trim();
    if (typeof body.issuer === "string") next.issuer = body.issuer.trim();
    if (typeof body.client_id === "string") next.client_id = body.client_id;
    if (typeof body.scopes === "string") next.scopes = body.scopes;
    if (typeof body.enabled === "boolean") next.enabled = body.enabled;
    if (typeof body.auto_provision === "boolean") {
      next.auto_provision = body.auto_provision;
    }
    if (typeof body.client_secret === "string" && body.client_secret !== "") {
      next.client_secret_set = true;
    }
    const url = (() => {
      try {
        return new URL(next.issuer);
      } catch {
        return null;
      }
    })();
    const secure =
      url !== null &&
      (url.protocol === "https:" ||
        (url.protocol === "http:" && url.hostname === "localhost"));
    return !secure || next.label === "" || next.client_id === "" ? null : next;
  };

  return [
    ...createOrgRoutes(getWorld),
    ...createPeopleRoutes(getWorld).map((route) => ({
      ...route,
      handler: guarded(route.handler),
    })),
    ...createOpsRoutes(getWorld),
    ...createInstallRoutes(getWorld),
    {
      method: "GET",
      pattern: "/settings/registration",
      handler: guarded(() => demoJson(state().registration)),
    },
    {
      method: "PUT",
      pattern: "/settings/registration",
      handler: guarded((req) => {
        const s = state();
        const body = (req.body ?? {}) as Record<string, unknown>;
        const mode = body.registration_mode;
        const domains = body.registration_domains;
        const approval = body.require_approval;
        const f = s.registration.fields;
        if (
          (mode != null && f["auth.registration_mode"]?.locked) ||
          (domains != null && f["auth.registration_domains"]?.locked) ||
          (approval != null && f["auth.require_approval"]?.locked)
        ) {
          return locked();
        }
        const next = { ...s.registration };
        const fields = { ...f };
        if (mode != null) {
          if (!MODES.includes(mode as RegistrationMode)) return invalid();
          next.registration_mode = mode as RegistrationMode;
          fields["auth.registration_mode"] = admin("admin");
        }
        if (Array.isArray(domains)) {
          next.registration_domains = [
            ...new Set(domains.map((d) => str(d).trim().toLowerCase())),
          ].filter((d) => d !== "");
          fields["auth.registration_domains"] = admin("admin");
        }
        if (typeof approval === "boolean") {
          next.require_approval = approval;
          fields["auth.require_approval"] = admin("admin");
        }
        if (
          next.registration_mode === "domains" &&
          next.registration_domains.length === 0
        ) {
          return invalid();
        }
        s.registration = { ...next, fields };
        syncBootstrap();
        return demoJson(s.registration);
      }),
    },
    {
      method: "GET",
      pattern: "/settings/auth",
      handler: guarded(() => demoJson(authView())),
    },
    {
      method: "PUT",
      pattern: "/settings/auth",
      handler: guarded((req) => {
        const s = state();
        const { password_enabled: value } = (req.body ?? {}) as Record<
          string,
          unknown
        >;
        if (typeof value !== "boolean") return demoJson(authView());
        if (s.auth.fields["auth.password_enabled"]?.locked) return locked();
        if (!value && enabledCount() === 0) return lastMethod();
        s.auth = {
          password_enabled: value,
          fields: { "auth.password_enabled": admin("admin") },
        };
        syncBootstrap();
        return demoJson(authView());
      }),
    },
    {
      method: "GET",
      pattern: "/settings/smtp",
      handler: guarded(() => demoJson(state().smtp)),
    },
    {
      method: "PUT",
      pattern: "/settings/smtp",
      handler: guarded((req) => {
        const s = state();
        const body = (req.body ?? {}) as Record<string, unknown>;
        const keys = [
          "host",
          "port",
          "security",
          "username",
          "password",
          "from_address",
          "from_name",
        ] as const;
        for (const key of keys) {
          if (body[key] != null && s.smtp.fields[`smtp.${key}`]?.locked) {
            return locked();
          }
        }
        const next = { ...s.smtp };
        const fields = { ...s.smtp.fields };
        const touch = (key: (typeof keys)[number]) => {
          fields[`smtp.${key}`] = admin("admin");
        };
        if (typeof body.host === "string") {
          next.host = body.host === "" ? null : body.host;
          touch("host");
        }
        if (typeof body.port === "number") {
          if (body.port < 1 || body.port > 65535) return invalid();
          next.port = body.port;
          touch("port");
        }
        if (
          body.security === "starttls" ||
          body.security === "tls" ||
          body.security === "none"
        ) {
          next.security = body.security;
          touch("security");
        }
        if (typeof body.username === "string") {
          next.username = body.username === "" ? null : body.username;
          touch("username");
        }
        if (typeof body.password === "string" && body.password !== "") {
          next.password_set = true;
          touch("password");
        }
        if (typeof body.from_address === "string") {
          next.from_address = body.from_address;
          touch("from_address");
        }
        if (typeof body.from_name === "string") {
          next.from_name = body.from_name;
          touch("from_name");
        }
        next.enabled = next.host !== null;
        s.smtp = { ...next, fields };
        syncBootstrap();
        return demoJson(s.smtp);
      }),
    },
    {
      method: "POST",
      pattern: "/settings/smtp/test",
      handler: guarded((req) => {
        const { smtp } = state();
        const to = str(((req.body ?? {}) as Record<string, unknown>).to);
        if (!smtp.enabled) {
          return demoJson({ ok: false, error: "SMTP is not configured" });
        }
        if ((smtp.host ?? "").includes("fail") || to.startsWith("fail@")) {
          return demoJson({
            ok: false,
            error: "SMTPConnectError: connection refused",
          });
        }
        return demoJson({ ok: true, error: null });
      }),
    },
    {
      method: "GET",
      pattern: "/oidc-providers",
      handler: guarded(() => demoJson(state().providers)),
    },
    {
      method: "POST",
      pattern: "/oidc-providers",
      handler: guarded((req) => {
        const body = (req.body ?? {}) as Record<string, unknown>;
        if (str(body.client_secret) === "") return invalid();
        const id = `p_${String(state().providers.length + 1)}${Math.random()
          .toString(36)
          .slice(2, 8)}`;
        const created = providerFrom(body, {
          id,
          label: "",
          issuer: "",
          client_id: "",
          client_secret_set: false,
          scopes: "openid email profile",
          enabled: true,
          auto_provision: false,
          created_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
        });
        if (!created) return invalid();
        state().providers = [...state().providers, created];
        syncBootstrap();
        return demoJson(created, 201);
      }),
    },
    {
      method: "PATCH",
      pattern: "/oidc-providers/:id",
      handler: guarded((req) => {
        const s = state();
        const current = s.providers.find((p) => p.id === req.params.id);
        if (!current) return demoError(404, "not_found", "Not Found");
        const updated = providerFrom(
          (req.body ?? {}) as Record<string, unknown>,
          current,
        );
        if (!updated) return invalid();
        const after = s.providers.map((p) =>
          p.id === current.id ? updated : p,
        );
        if (
          !s.auth.password_enabled &&
          after.filter((p) => p.enabled).length === 0
        ) {
          return lastMethod();
        }
        s.providers = after;
        syncBootstrap();
        return demoJson(updated);
      }),
    },
    {
      method: "DELETE",
      pattern: "/oidc-providers/:id",
      handler: guarded((req) => {
        const s = state();
        if (!s.providers.some((p) => p.id === req.params.id)) {
          return demoError(404, "not_found", "Not Found");
        }
        const after = s.providers.filter((p) => p.id !== req.params.id);
        if (
          !s.auth.password_enabled &&
          after.filter((p) => p.enabled).length === 0
        ) {
          return lastMethod();
        }
        s.providers = after;
        syncBootstrap();
        return demoNoContent();
      }),
    },
  ];
};
