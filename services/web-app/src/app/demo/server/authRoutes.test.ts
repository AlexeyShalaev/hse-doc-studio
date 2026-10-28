import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest, DemoResponse } from "@shared/api/demo";
import {
  ForgotResponseSchema,
  InvitationInfoSchema,
  RegisterResponseSchema,
} from "@entities/session";
import { activateServerScenario } from "./index";
import { serverDemoRoutes, setServerDemoActive } from "./routes";

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
const code = (res: DemoResponse) => (res.data as { code: string }).code;

const open = (over: Record<string, unknown> = {}) => ({
  ...(fixture("RegisterRequest", "open") as Record<string, unknown>),
  ...over,
});

describe("демо регистрации и ссылок из писем", () => {
  beforeEach(() => {
    setServerDemoActive(true);
  });

  it("открытый режим: нейтральный ответ без ссылки (SMTP есть)", async () => {
    activateServerScenario("registration_open");
    const res = await call("POST", "/auth/register", open());
    expect(res.status).toBe(200);
    expect(RegisterResponseSchema.parse(res.data)).toEqual(
      fixture("RegisterResponse", "check_email"),
    );
  });

  it("занятый адрес отвечает так же, как свободный", async () => {
    activateServerScenario("registration_open");
    const free = await call("POST", "/auth/register", open());
    const taken = await call(
      "POST",
      "/auth/register",
      open({ email: "taken@example.org" }),
    );
    expect(taken).toEqual(free);
  });

  it("открытый режим без SMTP: ссылка вместо письма", async () => {
    activateServerScenario("registration_open_nosmtp");
    const res = await call("POST", "/auth/register", open());
    const body = RegisterResponseSchema.parse(res.data);
    expect(body.status).toBe("check_email");
    expect(body.link).toMatch(/\/verify\/vf_/);
  });

  it("режим доменов: чужой домен отказ, свой проходит, approval@ ждёт", async () => {
    activateServerScenario("registration_domains");
    const bad = await call(
      "POST",
      "/auth/register",
      open({ email: "a@gmail.com" }),
    );
    expect(bad.status).toBe(403);
    expect(code(bad)).toBe("domain_not_allowed");
    const ok = await call(
      "POST",
      "/auth/register",
      open({ email: "a@hse.ru" }),
    );
    expect(RegisterResponseSchema.parse(ok.data).status).toBe("check_email");
    const approval = await call(
      "POST",
      "/auth/register",
      open({ email: "approval@example.org" }),
    );
    expect(RegisterResponseSchema.parse(approval.data)).toEqual(
      fixture("RegisterResponse", "pending_approval"),
    );
  });

  it("режим по приглашению: без токена отказ, с токеном проходит", async () => {
    activateServerScenario("admin_ready");
    const none = await call("POST", "/auth/register", open());
    expect(code(none)).toBe("invitation_required");
    const ok = await call(
      "POST",
      "/auth/register",
      fixture("RegisterRequest", "invited"),
    );
    expect(ok.status).toBe(200);
    const bad = await call(
      "POST",
      "/auth/register",
      open({ invitation_token: "inv_expired" }),
    );
    expect(bad.status).toBe(400);
    expect(code(bad)).toBe("invitation_invalid");
  });

  it("закрытый режим: отказ registration_closed", async () => {
    activateServerScenario("registration_closed");
    const res = await call("POST", "/auth/register", open());
    expect(res.status).toBe(403);
    expect(code(res)).toBe("registration_closed");
  });

  it("слабый пароль и лимит", async () => {
    activateServerScenario("registration_open");
    expect(
      code(await call("POST", "/auth/register", open({ password: "short" }))),
    ).toBe("password_policy");
    const limited = await call(
      "POST",
      "/auth/register",
      open({ email: "limited@example.org" }),
    );
    expect(limited.status).toBe(429);
  });

  it("приглашение: данные по эталону, просроченное отказ", async () => {
    activateServerScenario("registration_open");
    const ok = await call("GET", "/auth/invitations/inv_demo");
    expect(InvitationInfoSchema.parse(ok.data)).toEqual(
      fixture("InvitationInfo", "org"),
    );
    const plain = await call("GET", "/auth/invitations/inv_plain");
    expect(plain.data).toEqual(fixture("InvitationInfo", "plain"));
    const bad = await call("GET", "/auth/invitations/inv_expired");
    expect(code(bad)).toBe("invitation_invalid");
  });

  it("подтверждение: действующий токен 204, просроченный token_invalid", async () => {
    activateServerScenario("registration_open");
    expect(
      (
        await call(
          "POST",
          "/auth/verify",
          fixture("VerifyEmailRequest", "token"),
        )
      ).status,
    ).toBe(204);
    const bad = await call("POST", "/auth/verify", { token: "vf_expired" });
    expect(bad.status).toBe(400);
    expect(code(bad)).toBe("token_invalid");
  });

  it("повторная отправка: нейтральный ответ, ссылка только без SMTP", async () => {
    activateServerScenario("registration_open");
    const smtp = await call(
      "POST",
      "/auth/verify/resend",
      fixture("ResendVerificationRequest", "email"),
    );
    expect(ForgotResponseSchema.parse(smtp.data)).toEqual(
      fixture("ForgotResponse", "neutral"),
    );
    activateServerScenario("registration_open_nosmtp");
    const none = await call("POST", "/auth/verify/resend", {
      email: "a@b.org",
    });
    expect(ForgotResponseSchema.parse(none.data).link).toMatch(/\/verify\//);
  });

  it("forgot: ответ не зависит от адреса и совпадает с эталоном", async () => {
    activateServerScenario("registration_open");
    const known = await call(
      "POST",
      "/auth/forgot",
      fixture("ForgotRequest", "email"),
    );
    const unknown = await call("POST", "/auth/forgot", {
      email: "nobody@example.org",
    });
    expect(known).toEqual(unknown);
    expect(ForgotResponseSchema.parse(known.data)).toEqual(
      fixture("ForgotResponse", "neutral"),
    );
    activateServerScenario("registration_open_nosmtp");
    const link = await call("POST", "/auth/forgot", { email: "a@b.org" });
    expect(ForgotResponseSchema.parse(link.data).link).toMatch(/\/reset\//);
  });

  it("reset: токен, политика пароля и успех", async () => {
    activateServerScenario("registration_open");
    const ok = await call(
      "POST",
      "/auth/reset",
      fixture("ResetRequest", "token"),
    );
    expect(ok.status).toBe(204);
    const expired = await call("POST", "/auth/reset", {
      token: "rs_expired",
      password: "a much longer new passphrase",
    });
    expect(code(expired)).toBe("token_invalid");
    const weak = await call("POST", "/auth/reset", {
      token: "rs_ok",
      password: "short",
    });
    expect(code(weak)).toBe("password_policy");
  });
});
