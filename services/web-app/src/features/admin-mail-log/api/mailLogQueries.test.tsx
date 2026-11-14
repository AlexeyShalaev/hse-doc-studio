import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { ApiError, adminClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { mailLogApi } from "./mailLogApi";
import {
  isMailLogNotFound,
  mailLogKeys,
  useMailLog,
  useMailLogEntry,
  useMailLogSummary,
} from "./mailLogQueries";
import {
  MAIL_BUSY_COUNT,
  MAIL_PEOPLE,
  MAIL_PROJECTS,
  createMailLogDemo,
  type MailJournalProfile,
} from "../testing";

// Журнал писем на моках (mail-log.md, 6.1 и 6.3): адреса, фильтры по И, курсор, коды ошибок и
// хуки экранов W2 и W3.

let profile: MailJournalProfile = "default";
let smtp = true;
let actor: { id: string; name: string; admin: boolean } | null = {
  id: MAIL_PEOPLE.admin.id,
  name: MAIL_PEOPLE.admin.name,
  admin: true,
};
const NOW = Date.parse("2026-11-11T10:00:00Z");
const demo = createMailLogDemo({
  getActor: () => actor,
  profile: () => profile,
  smtpConfigured: () => smtp,
  now: () => NOW,
});

const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrap =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
const codeOf = async (promise: Promise<unknown>): Promise<string | null> => {
  try {
    await promise;
    return null;
  } catch (error) {
    return error instanceof ApiError ? error.code : String(error);
  }
};

beforeAll(() => {
  installDemoAdapter(adminClient, createDemoRouter(demo.routes));
});

beforeEach(() => {
  demo.reset();
  profile = "default";
  smtp = true;
  actor = {
    id: MAIL_PEOPLE.admin.id,
    name: MAIL_PEOPLE.admin.name,
    admin: true,
  };
});

describe("API журнала писем на моках", () => {
  it("страница без фильтров с оценкой числа, новые сверху", async () => {
    const page = await mailLogApi.page({ limit: 50 });
    expect(page.items.length).toBe(demo.journal().length);
    expect(page.total_estimate).toBe(demo.journal().length);
    expect(page.next_cursor).toBeNull();
    const ids = page.items.map((e) => e.id);
    expect(ids).toEqual([...ids].sort((a, b) => b - a));
  });

  it("курсор листает без повторов и пропусков", async () => {
    const seen: number[] = [];
    let cursor: string | undefined;
    for (let i = 0; i < 10; i += 1) {
      const page = await mailLogApi.page(
        cursor ? { limit: 7, cursor } : { limit: 7 },
      );
      seen.push(...page.items.map((e) => e.id));
      if (!page.next_cursor) break;
      cursor = page.next_cursor;
    }
    expect(seen).toEqual(demo.journal().map((r) => r.entry.id));
  });

  it("фильтры сочетаются по И, при фильтрах оценки числа нет", async () => {
    const failed = await mailLogApi.page({ status: ["failed"] });
    expect(failed.items.every((e) => e.status === "failed")).toBe(true);
    expect(failed.total_estimate).toBeNull();

    const both = await mailLogApi.page({
      status: ["sent", "failed"],
      template: ["project_invitation_link"],
    });
    expect(both.items.length).toBeGreaterThan(1);
    expect(
      both.items.every(
        (e) =>
          e.template === "project_invitation_link" &&
          (e.status === "sent" || e.status === "failed"),
      ),
    ).toBe(true);

    const maria = await mailLogApi.page({ recipient_id: MAIL_PEOPLE.maria.id });
    expect(maria.items.length).toBeGreaterThan(0);
    expect(
      maria.items.every((e) => e.to_user?.id === MAIL_PEOPLE.maria.id),
    ).toBe(true);

    const exact = await mailLogApi.page({
      recipient: "REJECT-X@example.org",
    });
    expect(exact.items.map((e) => e.to_email)).toEqual([
      "reject-x@example.org",
    ]);

    const bertie = await mailLogApi.page({
      project_id: MAIL_PROJECTS.bertie.id,
      reason: "recipient_refused",
      retrying: "false",
    });
    expect(bertie.items).toHaveLength(1);
    // Ждёт автоповтора (451): отдельный фильтр, как у сервера (14, V13).
    const waiting = await mailLogApi.page({ retrying: "true" });
    expect(waiting.items.map((e) => e.failure?.smtp_code)).toEqual([451]);
    await expect(mailLogApi.page({ retrying: "maybe" })).rejects.toThrow();

    const unknownTemplate = await mailLogApi.page({
      template: ["weekly_digest"],
    });
    expect(unknownTemplate.items[0]?.template_known).toBe(false);
  });

  it("поиск по адресу и теме, период: from включительно, to не включая", async () => {
    const byAddress = await mailLogApi.page({ q: "OLEG.mironov" });
    expect(byAddress.items.length).toBeGreaterThan(0);
    expect(
      byAddress.items.every((e) => e.to_email === MAIL_PEOPLE.oleg.email),
    ).toBe(true);
    const bySubject = await mailLogApi.page({ q: "напоминание" });
    expect(
      bySubject.items.every((e) => e.template === "signing_reminder"),
    ).toBe(true);

    const first = demo.journal()[0]?.entry;
    if (!first) throw new Error("пустой журнал");
    const exactly = await mailLogApi.page({ from: first.at, to: first.at });
    expect(exactly.items).toEqual([]);
    const fromIt = await mailLogApi.page({ from: first.at });
    expect(fromIt.items.map((e) => e.id)).toEqual([first.id]);
  });

  it("422 на неизвестный итог, неверный курсор, перевёрнутый период и лишний параметр", async () => {
    expect(await codeOf(mailLogApi.page({ status: ["sending"] }))).toBe(
      "input_invalid",
    );
    expect(await codeOf(mailLogApi.page({ cursor: "%%%" }))).toBe(
      "input_invalid",
    );
    expect(
      await codeOf(
        mailLogApi.page({
          from: "2026-11-11T00:00:00Z",
          to: "2026-11-10T00:00:00Z",
        }),
      ),
    ).toBe("input_invalid");
    expect(await codeOf(mailLogApi.page({ sort: "-at" }))).toBe(
      "input_invalid",
    );
    expect(await codeOf(mailLogApi.page({ template: ["Bad-Kind"] }))).toBe(
      "input_invalid",
    );
    expect(await codeOf(mailLogApi.page({ limit: 0 }))).toBe("input_invalid");
  });

  it("карточка с превью и 404 для удалённой строки", async () => {
    const record = demo.journal().find((r) => r.link === "token");
    if (!record) throw new Error("нет письма с токеном");
    const detail = await mailLogApi.entry(record.entry.id);
    expect(detail.entry).toEqual(record.entry);
    expect(detail.link_hidden).toBe(true);
    expect(detail.preview?.html).not.toMatch(/href=/);
    expect(await codeOf(mailLogApi.entry(999_999))).toBe("not_found");
  });

  it("сводка за сутки и плашка без SMTP", async () => {
    const summary = await mailLogApi.summary();
    expect(summary).toMatchObject({
      smtp_configured: true,
      window_hours: 24,
      failed: 3,
      retrying: 1,
      retention_days: 90,
    });
    smtp = false;
    expect((await mailLogApi.summary()).smtp_configured).toBe(false);
  });

  it("пустой журнал", async () => {
    profile = "empty";
    const page = await mailLogApi.page({});
    expect(page).toEqual({ items: [], next_cursor: null, total_estimate: 0 });
    expect(await mailLogApi.summary()).toMatchObject({
      sent: 0,
      failed: 0,
      not_sent: 0,
      suppressed: 0,
      last_failure: null,
    });
  });

  it("большой журнал листается страницами по 200", async () => {
    profile = "busy";
    const page = await mailLogApi.page({ limit: 200 });
    expect(page.items).toHaveLength(200);
    expect(page.total_estimate).toBe(MAIL_BUSY_COUNT);
    expect(page.next_cursor).not.toBeNull();
  });

  it("не админу 404, анониму 401", async () => {
    actor = { id: "u_x", name: "X", admin: false };
    expect(await codeOf(mailLogApi.page({}))).toBe("not_found");
    expect(await codeOf(mailLogApi.summary())).toBe("not_found");
    actor = null;
    expect(await codeOf(mailLogApi.page({}))).toBe("auth_required");
    expect(await codeOf(mailLogApi.entry(1))).toBe("auth_required");
  });

  it("новая попытка дописывается сверху", async () => {
    const before = demo.journal()[0]?.entry.id ?? 0;
    const record = demo.record({
      template: "smtp_test",
      to: MAIL_PEOPLE.admin,
      subject: "HSE Doc Studio: проверка почты",
      status: "sent",
      cause: "user",
      actor: MAIL_PEOPLE.admin,
      origin: "smtp_test",
    });
    expect(record.entry.id).toBe(before + 1);
    const page = await mailLogApi.page({ limit: 1 });
    expect(page.items[0]?.id).toBe(record.entry.id);
    expect(page.items[0]?.message_id).not.toBeNull();
  });
});

describe("хуки журнала писем", () => {
  it("useMailLog: первая страница и «Показать ещё»", async () => {
    const client = makeClient();
    const { result } = renderHook(() => useMailLog({ params: { limit: 10 } }), {
      wrapper: wrap(client),
    });
    await waitFor(() => {
      expect(result.current.items).toHaveLength(10);
    });
    expect(result.current.hasMore).toBe(true);
    expect(result.current.totalEstimate).toBe(demo.journal().length);
    act(() => {
      result.current.loadMore();
    });
    await waitFor(() => {
      expect(result.current.items).toHaveLength(20);
    });
    expect(
      client.getQueryCache().findAll({ queryKey: mailLogKeys.all }).length,
    ).toBeGreaterThan(0);
  });

  it("useMailLog: фильтр из состояния адреса", async () => {
    const { result } = renderHook(
      () => useMailLog({ params: { limit: 50, status: ["suppressed"] } }),
      { wrapper: wrap(makeClient()) },
    );
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.items.map((e) => e.reason).sort()).toEqual([
      "account_blocked",
      "email_unverified",
    ]);
  });

  it("useMailLogEntry: null не ходит на сервер, 404 без повтора", async () => {
    const client = new QueryClient();
    const closed = renderHook(() => useMailLogEntry(null), {
      wrapper: wrap(client),
    });
    expect(closed.result.current.fetchStatus).toBe("idle");

    const { result } = renderHook(() => useMailLogEntry(999_999), {
      wrapper: wrap(client),
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(isMailLogNotFound(result.current.error)).toBe(true);
    expect(result.current.failureCount).toBe(1);

    const id = demo.journal()[0]?.entry.id ?? 0;
    const found = renderHook(() => useMailLogEntry(id), {
      wrapper: wrap(client),
    });
    await waitFor(() => {
      expect(found.result.current.data?.entry.id).toBe(id);
    });
  });

  it("useMailLogSummary: сводка за сутки", async () => {
    profile = "auth_failure";
    const { result } = renderHook(() => useMailLogSummary(), {
      wrapper: wrap(makeClient()),
    });
    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });
    expect(result.current.data?.last_failure?.reason).toBe("auth");
    expect(result.current.data?.failed).toBe(5);
  });
});
