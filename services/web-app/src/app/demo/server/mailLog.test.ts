import { beforeEach, describe, expect, it } from "vitest";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest, DemoResponse, DemoRoute } from "@shared/api/demo";
import {
  MailLogDetailSchema,
  MailLogPageSchema,
  MailLogSummarySchema,
} from "@features/admin-mail-log";
import { MAIL_BUSY_COUNT } from "@features/admin-mail-log/testing";
import { activateServerScenario } from "./index";
import {
  getServerWorld,
  serverAdminDemoRoutes,
  setServerDemoActive,
} from "./routes";

// Демо-мир отвечает на адреса раздела 6 mail-log.md по сценариям: экраны W2 и W3 ведутся на нём
// до слияния бэкенда (B1..B6).

const caller = (routes: DemoRoute[]) => {
  const router = createDemoRouter(routes);
  return async (
    method: DemoRequest["method"],
    path: string,
    query: DemoRequest["query"] = {},
    body?: unknown,
  ): Promise<DemoResponse> => {
    const found = router.match(method, path);
    if (!found) throw new Error(`no demo route ${method} ${path}`);
    return found.handler({
      method,
      path,
      params: found.params,
      query,
      body,
      forward: () => Promise.reject(new Error("forward")),
    });
  };
};
const admin = caller(serverAdminDemoRoutes);
const codeOf = (r: DemoResponse) => (r.data as { code?: string }).code;
const page = async (query: DemoRequest["query"] = {}) =>
  MailLogPageSchema.parse((await admin("GET", "/mail-log", query)).data);
const summary = async () =>
  MailLogSummarySchema.parse((await admin("GET", "/mail-log/summary")).data);

describe("демо: журнал писем по сценариям", () => {
  beforeEach(() => {
    setServerDemoActive(true);
  });

  it("обычная установка: все итоги за сутки, карточка с превью", async () => {
    activateServerScenario("admin_ready");
    const s = await summary();
    expect(s.smtp_configured).toBe(true);
    expect(s.sent).toBeGreaterThan(0);
    expect(s.failed).toBeGreaterThan(0);
    expect(s.suppressed).toBeGreaterThan(0);
    const first = (await page({ limit: "5" })).items[0];
    if (!first) throw new Error("пустой журнал");
    const detail = MailLogDetailSchema.parse(
      (await admin("GET", `/mail-log/${String(first.id)}`)).data,
    );
    expect(detail.entry).toEqual(first);
    expect(codeOf(await admin("GET", "/mail-log/999999"))).toBe("not_found");
    expect(codeOf(await admin("GET", "/mail-log/abc"))).toBe("input_invalid");
  });

  it("почта не настроена: плашка и строки «почта не настроена»", async () => {
    activateServerScenario("admin_sso");
    const s = await summary();
    expect(s.smtp_configured).toBe(false);
    expect(s.not_sent).toBeGreaterThan(0);
    expect(s.sent + s.failed).toBe(0);
    const skipped = await page({ status: "not_sent" });
    expect(skipped.items.every((e) => e.reason === "smtp_off")).toBe(true);
  });

  it("сбой входа на SMTP: последний сбой класса auth", async () => {
    activateServerScenario("ops_services_degraded");
    expect((await summary()).last_failure?.reason).toBe("auth");
  });

  it("свежая установка: писем ещё не было", async () => {
    activateServerScenario("ops_fresh");
    expect(await page()).toEqual({
      items: [],
      next_cursor: null,
      total_estimate: 0,
    });
  });

  it("большой мир: журнал листается по курсору", async () => {
    activateServerScenario("admin_scale");
    const first = await page({ limit: "200" });
    expect(first.total_estimate).toBe(MAIL_BUSY_COUNT);
    expect(first.next_cursor).not.toBeNull();
    const second = await page({
      limit: "200",
      cursor: first.next_cursor ?? "",
    });
    expect(second.items[0]?.id).toBeLessThan(first.items.at(-1)?.id ?? 0);
  });

  it("выключили почту в «Почта (SMTP)»: сводка показывает плашку", async () => {
    activateServerScenario("admin_ready");
    expect(
      (await admin("PUT", "/settings/smtp", {}, { host: "" })).status,
    ).toBe(200);
    expect((await summary()).smtp_configured).toBe(false);
  });

  it("тестовое письмо дописывает строку в журнал", async () => {
    activateServerScenario("admin_ready");
    const before = (await page({ limit: "1" })).items[0]?.id ?? 0;
    const to = getServerWorld().bootstrap.user?.email ?? "";
    await admin("POST", "/settings/smtp/test", {}, { to });
    const sent = (await page({ limit: "1" })).items[0];
    expect(sent).toMatchObject({
      id: before + 1,
      template: "smtp_test",
      status: "sent",
      origin: "smtp_test",
      cause: "user",
    });
    expect(sent?.to_user?.email).toBe(to);

    await admin("POST", "/settings/smtp/test", {}, { to: "fail@example.org" });
    const failed = (await page({ limit: "1" })).items[0];
    expect(failed).toMatchObject({
      status: "failed",
      reason: "connect",
      to_email: "fail@example.org",
      to_user: null,
    });
  });

  it("не админу журнала нет", async () => {
    activateServerScenario("student_ready");
    expect(codeOf(await admin("GET", "/mail-log"))).toBe("not_found");
    expect(codeOf(await admin("GET", "/mail-log/summary"))).toBe("not_found");
  });
});
