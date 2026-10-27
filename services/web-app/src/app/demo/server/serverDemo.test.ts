import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest, DemoResponse } from "@shared/api/demo";
import {
  BootstrapSchema,
  LoginResponseSchema,
  ServerSetupStatusSchema,
} from "@entities/session";
import { activateServerScenario } from "./index";
import { serverDemoRoutes, setServerDemoActive } from "./routes";
import { SERVER_SCENARIOS } from "./scenarios";

// Демо серверного мира обязано отдавать ту же форму, что настоящий бэкенд: ответы
// проходят zod-схемы, а сценарии с эталоном совпадают с файлами contracts/server.

const FIXTURES = join(
  import.meta.dirname,
  ...Array<string>(6).fill(".."),
  "contracts",
  "server",
  "fixtures",
);
const fixture = (schema: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, schema, `${name}.json`), "utf8"));

const router = createDemoRouter(serverDemoRoutes);

const call = async (
  method: DemoRequest["method"],
  path: string,
  body?: unknown,
): Promise<DemoResponse> => {
  const found = router.match(method, path);
  if (!found) throw new Error(`no demo route ${method} ${path}`);
  return found.handler({
    method,
    path,
    params: found.params,
    query: {},
    body,
    forward: () => Promise.reject(new Error("forward")),
  });
};

const FIXTURE_OF: Record<string, string> = {
  fresh_install: "server_needs_admin",
  admin_ready: "server_admin",
  student_ready: "server_user",
  sso_only: "server_sso_only",
};

describe("серверное демо", () => {
  beforeEach(() => {
    setServerDemoActive(true);
    activateServerScenario("student_ready");
  });

  it.each(SERVER_SCENARIOS.map((s) => s.id))(
    "bootstrap сценария %s проходит zod",
    async (id) => {
      activateServerScenario(id);
      const response = await call("GET", "/session/bootstrap");
      expect(BootstrapSchema.parse(response.data).mode).toBe("server");
    },
  );

  it.each(Object.entries(FIXTURE_OF))(
    "сценарий %s совпадает с эталоном %s",
    async (id, name) => {
      activateServerScenario(id);
      const response = await call("GET", "/session/bootstrap");
      expect(response.data).toEqual(fixture("Bootstrap", name));
    },
  );

  it("регистрация закрыта: форма регистрации не предлагается", async () => {
    activateServerScenario("registration_closed");
    const response = await call("GET", "/session/bootstrap");
    expect(BootstrapSchema.parse(response.data).auth.registration_mode).toBe(
      "closed",
    );
  });

  it("смена сценария меняет ответ bootstrap", async () => {
    activateServerScenario("admin_ready");
    const admin = BootstrapSchema.parse(
      (await call("GET", "/session/bootstrap")).data,
    );
    activateServerScenario("sso_only");
    const sso = BootstrapSchema.parse(
      (await call("GET", "/session/bootstrap")).data,
    );
    expect(admin.user?.is_instance_admin).toBe(true);
    expect(sso.user).toBeNull();
    expect(sso.auth.password_enabled).toBe(false);
  });

  it("вход и выход меняют сессию и проходят схемы", async () => {
    activateServerScenario("registration_closed");
    const bad = await call("POST", "/auth/login", {
      email: "anna.petrova@example.org",
      password: "short",
    });
    expect(bad.status).toBe(401);
    expect((bad.data as { code: string }).code).toBe("invalid_credentials");

    const ok = await call(
      "POST",
      "/auth/login",
      fixture("LoginRequest", "password"),
    );
    expect(ok.status).toBe(200);
    expect(LoginResponseSchema.parse(ok.data).user.email).toBe(
      "anna.petrova@example.org",
    );
    const after = BootstrapSchema.parse(
      (await call("GET", "/session/bootstrap")).data,
    );
    expect(after.csrf_token).not.toBeNull();

    expect((await call("POST", "/auth/logout")).status).toBe(204);
    const out = BootstrapSchema.parse(
      (await call("GET", "/session/bootstrap")).data,
    );
    expect(out.user).toBeNull();
    expect(out.csrf_token).toBeNull();
  });

  it("при SSO-only вход паролем закрыт", async () => {
    activateServerScenario("sso_only");
    const response = await call(
      "POST",
      "/auth/login",
      fixture("LoginRequest", "password"),
    );
    expect(response.status).toBe(403);
    const code = (response.data as { code: string }).code;
    expect(code).toBe("sso_login_required");
    const codes = JSON.parse(
      readFileSync(join(FIXTURES, "..", "error_codes.json"), "utf8"),
    ) as string[];
    expect(codes).toContain(code);
  });

  it("статус мастера совпадает со схемой", async () => {
    activateServerScenario("fresh_install");
    const status = ServerSetupStatusSchema.parse(
      (await call("GET", "/server-setup/status")).data,
    );
    expect(status).toEqual(fixture("ServerSetupStatus", "needs_admin"));
  });

  it("пока демо выключено, запрос уходит настоящему бэкенду", async () => {
    setServerDemoActive(false);
    await expect(call("GET", "/session/bootstrap")).rejects.toThrow("forward");
  });
});
