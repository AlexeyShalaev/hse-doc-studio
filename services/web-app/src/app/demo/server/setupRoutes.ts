import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type { RegistrationMode, SetupSettingKey } from "@entities/session";
import { ADMIN_CSRF, DEMO_ADMIN, DEMO_SETUP_TOKEN } from "./scenarios";
import type { ServerDemoWorld } from "./world";

// Демо мастера первого запуска. Тела ответов совпадают с contracts/server/fixtures
// (ServerSetupStatus, ServerSetupSettings, ServerSetupEnvironment, LoginResponse).
//
// Особые значения, чтобы вызывать каждое состояние руками:
//  - токен установки st_7Fk2Rn5DxQ8WbHa1 (другой: setup_token_invalid);
//  - адрес race@example.org: админ уже создан другим, ответ setup_already_done;
//  - пароль, начинающийся с password: password_policy;
//  - сценарии установки сами задают, что взято из окружения и упало ли хранилище.

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";
const WEAK_PASSWORD = /^(password|qwerty|12345)/i;

export const createSetupRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const status = () => {
    const { setup, bootstrap, scenario } = getWorld();
    const locksMode = setup.locked.includes("registration_mode");
    return {
      state: bootstrap.setup_state,
      token_required: !setup.adminExists && scenario.tokenRequired,
      steps_done:
        bootstrap.setup_state === "ready"
          ? ["admin", "settings"]
          : [
              ...(setup.adminExists ? ["admin"] : []),
              ...(setup.settingsDone || locksMode ? ["settings"] : []),
            ],
    };
  };
  const closed = () => getWorld().setup.completed;
  const notFound = () => demoError(404, "not_found", "Not Found");
  /** Шаги после создания админа идут его сессией: аноним 401, обычный человек 403. */
  const denied = () => {
    const { user } = getWorld().bootstrap;
    if (user === null)
      return demoError(401, "auth_required", "Authentication required");
    return user.is_instance_admin
      ? null
      : demoError(403, "forbidden", "Forbidden");
  };

  return [
    {
      method: "GET",
      pattern: "/server-setup/status",
      handler: () => (closed() ? notFound() : demoJson(status())),
    },
    {
      method: "POST",
      pattern: "/server-setup/admin",
      handler: (req) => {
        const world = getWorld();
        if (closed()) return notFound();
        const body = (req.body ?? {}) as Record<string, unknown>;
        const email = str(body.email).trim();
        if (
          world.setup.adminExists ||
          email.toLowerCase() === "race@example.org"
        ) {
          world.setup.adminExists = true;
          return demoError(
            409,
            "setup_already_done",
            "The first administrator already exists",
          );
        }
        if (
          world.scenario.tokenRequired &&
          str(body.setup_token) !== DEMO_SETUP_TOKEN
        ) {
          return demoError(
            403,
            "setup_token_invalid",
            "Setup token is invalid",
          );
        }
        const password = str(body.password);
        if (
          password.length < world.bootstrap.auth.password_min_length ||
          WEAK_PASSWORD.test(password)
        ) {
          return demoError(422, "password_policy", "Password is too weak");
        }
        const name = str(body.name).trim();
        const initials = name
          .split(/\s+/)
          .slice(0, 2)
          .map((word) => word.charAt(0).toUpperCase())
          .join("");
        const user = {
          ...DEMO_ADMIN,
          name,
          email,
          avatar_initials: initials || DEMO_ADMIN.avatar_initials,
          org_roles: [],
        };
        world.setup.adminExists = true;
        world.adminCreated = true;
        world.bootstrap = {
          ...world.bootstrap,
          user,
          capabilities: { ...world.bootstrap.capabilities, admin: true },
          csrf_token: ADMIN_CSRF,
        };
        return demoJson({ user, csrf_token: ADMIN_CSRF });
      },
    },
    {
      method: "GET",
      pattern: "/server-setup/settings",
      handler: () => {
        if (closed()) return notFound();
        const refusal = denied();
        if (refusal) return refusal;
        const { setup } = getWorld();
        return demoJson({
          ...setup.settings,
          locked_by_env: setup.locked,
        });
      },
    },
    {
      method: "POST",
      pattern: "/server-setup/settings",
      handler: (req) => {
        if (closed()) return notFound();
        const refusal = denied();
        if (refusal) return refusal;
        const world = getWorld();
        const { setup } = world;
        const body = (req.body ?? {}) as Record<string, unknown>;
        const pick = <T>(key: SetupSettingKey, next: T, now: T): T =>
          setup.locked.includes(key) ? now : next;
        setup.settings = {
          registration_mode: pick(
            "registration_mode",
            str(body.registration_mode) as RegistrationMode,
            setup.settings.registration_mode,
          ),
          registration_domains: pick(
            "registration_domains",
            Array.isArray(body.registration_domains)
              ? body.registration_domains.map(str)
              : [],
            setup.settings.registration_domains,
          ),
          require_approval: pick(
            "require_approval",
            body.require_approval === true,
            setup.settings.require_approval,
          ),
          password_enabled: pick(
            "password_enabled",
            body.password_enabled !== false,
            setup.settings.password_enabled,
          ),
        };
        setup.settingsDone = true;
        world.bootstrap = {
          ...world.bootstrap,
          auth: {
            ...world.bootstrap.auth,
            registration_mode: setup.settings.registration_mode,
            password_enabled: setup.settings.password_enabled,
          },
        };
        return demoJson(status());
      },
    },
    {
      method: "GET",
      pattern: "/server-setup/environment",
      handler: () => {
        if (closed()) return notFound();
        const refusal = denied();
        if (refusal) return refusal;
        const { setup } = getWorld();
        return demoJson({
          checks: [
            { id: "database", status: "ok", reason: null },
            setup.storage === "ok"
              ? { id: "storage", status: "ok", reason: null }
              : {
                  id: "storage",
                  status: "fail",
                  reason: "ClientConnectorError",
                },
            { id: "runner", status: "not_configured", reason: null },
          ],
        });
      },
    },
    {
      method: "POST",
      pattern: "/server-setup/complete",
      handler: () => {
        if (closed()) return notFound();
        const refusal = denied();
        if (refusal) return refusal;
        const world = getWorld();
        world.setup.completed = true;
        world.bootstrap = { ...world.bootstrap, setup_state: "ready" };
        return demoJson({
          state: "ready",
          token_required: false,
          steps_done: ["admin", "settings"],
        });
      },
    },
  ];
};
