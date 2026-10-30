import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import { useServerDemoScenarioStore } from "./scenarioStore";
import { createAccountRoutes } from "./accountRoutes";
import { createAdminRoutes } from "./adminRoutes";
import { createAuthRoutes } from "./authRoutes";
import { catalogRoutes } from "./catalogRoutes";
import { createSharedProviderUserRoutes } from "./installRoutes";
import { createMemberOrgRoutes } from "./memberOrgRoutes";
import { createPersonalRoutes } from "./personalRoutes";
import { createProjectAccessRoutes } from "./projectAccessRoutes";
import { createProjectRoutes } from "./projectRoutes";
import { createSetupRoutes } from "./setupRoutes";
import { createSystemRoutes } from "./systemRoutes";
import { createServerWorld, signIn, signOut } from "./world";

// Серверное демо включается явно (VITE_SERVER_DEMO=1 или галерея /dev/server-screens).
// Пока оно выключено, обработчики отдают запрос дальше: демо git работает как раньше.
let active = false;
export const setServerDemoActive = (value: boolean): void => {
  active = value;
};
export const isServerDemoActive = (): boolean => active;

let world = createServerWorld(useServerDemoScenarioStore.getState().scenarioId);
export const getServerWorld = () => world;
export const resetServerWorld = (scenarioId: string): void => {
  world = createServerWorld(scenarioId);
};

const guarded =
  (handler: DemoRoute["handler"]): DemoRoute["handler"] =>
  (req) =>
    active
      ? handler(req)
      : req.forward().then((res) => ({
          status: res.status,
          data: res.data as unknown,
        }));

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

// Особые адреса демо: каждый возвращает свой отказ входа, чтобы все состояния экрана
// можно было вызвать руками.
const DEMO_LOGIN_REFUSALS: Record<
  string,
  {
    status: number;
    code: string;
    detail: string;
    extra?: Record<string, unknown>;
  }
> = {
  "locked@example.org": {
    status: 429,
    code: "rate_limited",
    detail: "Too many attempts",
    extra: { retry_after: 20 },
  },
  "unverified@example.org": {
    status: 403,
    code: "email_not_verified",
    detail: "Email is not verified",
  },
  "pending@example.org": {
    status: 403,
    code: "pending_approval",
    detail: "Account is pending approval",
  },
  "disabled@example.org": {
    status: 403,
    code: "account_disabled",
    detail: "Account is disabled",
  },
  "sso@example.org": {
    status: 403,
    code: "sso_login_required",
    detail: "Single sign-on required",
  },
};

const routes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/session/bootstrap",
    handler: () => demoJson(world.bootstrap),
  },
  {
    method: "POST",
    pattern: "/auth/login",
    handler: (req) => {
      const { auth } = world.bootstrap;
      const body = (req.body ?? {}) as Record<string, unknown>;
      if (!auth.password_enabled) {
        return demoError(
          403,
          "sso_login_required",
          "This email can only sign in through single sign-on",
        );
      }
      const refusal = DEMO_LOGIN_REFUSALS[str(body.email).trim().toLowerCase()];
      if (refusal) {
        return demoError(
          refusal.status,
          refusal.code,
          refusal.detail,
          refusal.extra,
        );
      }
      if (str(body.password).length < auth.password_min_length) {
        return demoError(
          401,
          "invalid_credentials",
          "Invalid email or password",
        );
      }
      const user = signIn(world, str(body.email));
      return demoJson({ user, csrf_token: world.bootstrap.csrf_token });
    },
  },
  {
    method: "POST",
    pattern: "/auth/logout",
    handler: () => {
      signOut(world);
      return demoNoContent();
    },
  },
];

const withGuard = (route: DemoRoute): DemoRoute => ({
  ...route,
  handler: guarded(route.handler),
});

/** Маршруты клиента /api/admin: ставятся на adminClient отдельно от /api/v1. */
export const serverAdminDemoRoutes: DemoRoute[] = createAdminRoutes(
  () => world,
).map(withGuard);

/** Маршруты клиента systemClient (/api/v1/system/*): у него свой транспорт. */
export const serverSystemDemoRoutes: DemoRoute[] = createSystemRoutes(
  () => world,
).map(withGuard);

export const serverDemoRoutes: DemoRoute[] = [
  ...routes,
  ...createAuthRoutes(() => world),
  ...createAccountRoutes(() => world),
  ...createSetupRoutes(() => world),
  ...createProjectRoutes(() => world),
  ...createProjectAccessRoutes(() => world),
  ...createMemberOrgRoutes(() => world),
  ...createPersonalRoutes(() => world),
  ...createSharedProviderUserRoutes(() => world),
  ...catalogRoutes,
].map((route) => ({
  ...route,
  handler: guarded(route.handler),
}));
