import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import {
  AdminJobPageSchema,
  AdminQueueSummarySchema,
  AdminQuotasSchema,
  AdminRunnerPageSchema,
  AdminRunnerSchema,
  AdminRunnerTokenCreatedSchema,
  AdminRunnerTokenPageSchema,
  AdminServiceHealthSchema,
  AdminStorageUsageSchema,
  type AdminRunner,
  type AdminRunnerToken,
  type AdminStorage,
} from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { serverAdminDemoRoutes } from "@/app/demo/server/routes";
import { formatBytes, formatDuration, percent } from "./lib/format";
import { busySlots } from "./lib/jobs";
import { personRef, shortRef } from "./lib/people";
import { ensureAdminOpsLocales } from "./lib/locales";
import { fromMinutes, toMinutes } from "./lib/minutes";
import {
  ONLINE_WITHIN_S,
  STALE_WITHIN_S,
  countOnline,
  runnerStatus,
} from "./lib/runnerStatus";
import { isLowSpace } from "./lib/storage";
import { tokenStatus } from "./lib/tokenStatus";
import { statusOf } from "./lib/viewStatus";
import { ApiError } from "@shared/api";
import { QuotasPage, RunnersPage, ServicesPage, StoragePage } from "./index";

// Операционные экраны поверх демо-транспорта: те же запросы, что уйдут настоящему бэкенду,
// и ответы, проходящие те же схемы.

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

const router = createDemoRouter(serverAdminDemoRoutes);
const call = async (
  method: DemoRequest["method"],
  path: string,
  body?: unknown,
  query: DemoRequest["query"] = {},
) => {
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
const NOW = Date.parse("2026-10-27T10:00:00Z");
const iso = (secondsAgo: number | null) =>
  secondsAgo === null ? null : new Date(NOW - secondsAgo * 1000).toISOString();
const runner = (
  seen: number | null,
  extra: Partial<AdminRunner> = {},
): AdminRunner => ({
  id: "r",
  name: "r",
  status: "offline",
  tags: [],
  concurrency: 1,
  resource_class: "standard",
  version: "1",
  created_at: iso(1000) ?? "",
  last_seen_at: iso(seen),
  paused: false,
  revoked: false,
  ...extra,
});

describe("операционные разделы: чистая логика", () => {
  it("статус раннера считается по last_seen_at", () => {
    expect(runnerStatus(runner(5), NOW)).toBe("online");
    expect(runnerStatus(runner(ONLINE_WITHIN_S), NOW)).toBe("online");
    expect(runnerStatus(runner(ONLINE_WITHIN_S + 1), NOW)).toBe("stale");
    expect(runnerStatus(runner(STALE_WITHIN_S), NOW)).toBe("stale");
    expect(runnerStatus(runner(STALE_WITHIN_S + 1), NOW)).toBe("offline");
    expect(runnerStatus(runner(null), NOW)).toBe("offline");
  });

  it("пауза и отзыв сильнее давности сигнала", () => {
    expect(runnerStatus(runner(1, { paused: true }), NOW)).toBe("paused");
    expect(runnerStatus(runner(1, { revoked: true, paused: true }), NOW)).toBe(
      "revoked",
    );
    expect(
      countOnline([runner(1), runner(1, { paused: true }), runner(9999)], NOW),
    ).toBe(1);
  });

  it("токен регистрации: действует, использован, истёк, отозван", () => {
    const token = (extra: Partial<AdminRunnerToken>): AdminRunnerToken => ({
      id: "t",
      label: "",
      created_at: iso(10) ?? "",
      expires_at: new Date(NOW + 1000).toISOString(),
      max_uses: 2,
      uses: 0,
      revoked: false,
      ...extra,
    });
    expect(tokenStatus(token({}), NOW)).toBe("active");
    expect(tokenStatus(token({ uses: 2 }), NOW)).toBe("exhausted");
    expect(tokenStatus(token({ expires_at: iso(1) }), NOW)).toBe("expired");
    expect(tokenStatus(token({ expires_at: null }), NOW)).toBe("active");
    expect(tokenStatus(token({ revoked: true, uses: 2 }), NOW)).toBe("revoked");
  });

  it("нет прав и отсутствие раздела дают отдельное состояние, а не ошибку", () => {
    const failed = (status: number, code: string) => ({
      data: undefined,
      isError: true,
      error: new ApiError(code, code, status),
    });
    expect(statusOf(failed(403, "forbidden"))).toBe("forbidden");
    expect(statusOf(failed(404, "not_found"))).toBe("forbidden");
    expect(statusOf(failed(500, "internal"))).toBe("error");
    expect(statusOf({ data: undefined, isError: false })).toBe("loading");
    expect(statusOf({ data: [], isError: false })).toBe("ready");
  });

  it("неудачный фоновый опрос не заменяет полученные данные ошибкой", () => {
    const stale = (status: number, code: string) => ({
      data: [],
      isError: true,
      error: new ApiError(code, code, status),
    });
    expect(statusOf(stale(500, "internal"))).toBe("ready");
    expect(statusOf(stale(403, "forbidden"))).toBe("ready");
  });

  it("люди по идентификатору: имя из справочника, без имени нейтрально", () => {
    const people = new Map([
      ["u1", { name: "Мария Келлер", email: "maria@example.org" }],
    ]);
    expect(personRef("u1", "", people)).toEqual({
      id: "u1",
      name: "Мария Келлер",
      email: "maria@example.org",
    });
    expect(personRef("u2", "  ", people)).toEqual({
      id: "u2",
      name: null,
      email: null,
    });
    expect(shortRef("p_01hxa1c4de")).toBe("a1c4de");
    expect(shortRef("3f2c9a1e-0000-4000-8000-00000a1c4de9")).toBe("1c4de9");
  });

  it("занятые места считаются по выполняющимся задачам раннера", () => {
    const slots = busySlots([
      { status: "running", runner_id: "r1" },
      { status: "running", runner_id: "r1" },
      { status: "running", runner_id: "r2" },
      { status: "queued", runner_id: null },
      { status: "succeeded", runner_id: "r2" },
    ]);
    expect(slots.get("r1")).toBe(2);
    expect(slots.get("r2")).toBe(1);
    expect(slots.has("r3")).toBe(false);
  });

  it("размеры, длительности и доли", () => {
    expect(formatBytes(0, "en")).toBe("0 B");
    expect(formatBytes(1536, "en")).toBe("1.5 KB");
    expect(formatBytes(5 * 1024 ** 3, "en")).toBe("5 GB");
    const units = { s: "с", min: "мин", h: "ч" };
    expect(formatDuration(45, units)).toBe("45 с");
    expect(formatDuration(125, units)).toBe("2 мин 5 с");
    expect(formatDuration(3780, units)).toBe("1 ч 3 мин");
    expect(percent(1, 4)).toBe(25);
    expect(percent(5, 0)).toBe(0);
  });

  it("минуты в форме и секунды в запросе", () => {
    expect(toMinutes(600)).toBe("10");
    expect(toMinutes(90)).toBe("1.5");
    expect(fromMinutes("1,5")).toBe(90);
    expect(fromMinutes("")).toBeNull();
    expect(fromMinutes("abc")).toBeNull();
  });

  it("мало места: меньше запаса или малая доля диска", () => {
    const GIB = 1024 ** 3;
    const base: AdminStorage = {
      blob_count: 0,
      blob_bytes: 0,
      projects: 0,
      deleted_projects: 0,
      free_bytes: 86 * GIB,
      volume_total_bytes: 100 * GIB,
      computed_at: iso(1) ?? "",
      owners: [],
    };
    expect(isLowSpace(base)).toBe(false);
    expect(isLowSpace({ ...base, free_bytes: 2 * GIB })).toBe(true);
    expect(isLowSpace({ ...base, free_bytes: null })).toBe(false);
    expect(
      isLowSpace({
        ...base,
        free_bytes: 6 * GIB,
        volume_total_bytes: 100 * GIB,
      }),
    ).toBe(true);
  });
});

describe("операционные разделы: демо-API", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(() => {
    activateServerScenario("admin_ready");
  });

  it("ответы проходят схемы контракта", async () => {
    AdminRunnerPageSchema.parse((await call("GET", "/runners")).data);
    AdminRunnerTokenPageSchema.parse(
      (await call("GET", "/runner-tokens")).data,
    );
    AdminJobPageSchema.parse((await call("GET", "/queue")).data);
    AdminQueueSummarySchema.parse((await call("GET", "/queue/summary")).data);
    AdminQuotasSchema.parse((await call("GET", "/quotas")).data);
    for (const s of (await call("GET", "/services")).data as unknown[]) {
      AdminServiceHealthSchema.parse(s);
    }
    AdminStorageUsageSchema.parse((await call("GET", "/storage")).data);
  });

  it("не админ получает 404, аноним 401", async () => {
    activateServerScenario("org_admin");
    expect((await call("GET", "/runners")).status).toBe(404);
    expect((await call("GET", "/queue")).status).toBe(404);
    activateServerScenario("fresh_install");
    expect((await call("GET", "/runners")).status).toBe(401);
  });

  it("секрет токена приходит только при создании", async () => {
    const created = await call("POST", "/runner-tokens", {
      label: "Стенд",
      ttl_hours: 24,
      max_uses: 1,
    });
    expect(created.status).toBe(201);
    const body = AdminRunnerTokenCreatedSchema.parse(created.data);
    expect(body.command).toContain(body.secret);
    const list = JSON.stringify((await call("GET", "/runner-tokens")).data);
    expect(list).not.toContain(body.secret);
    expect(list).toContain(body.token.id);
  });

  it("токен: неверные сроки, частота и отзыв", async () => {
    const bad = await call("POST", "/runner-tokens", {
      label: "",
      ttl_hours: 0,
      max_uses: 1,
    });
    expect(bad.status).toBe(422);
    const limited = await call("POST", "/runner-tokens", {
      label: "limit",
      ttl_hours: 1,
      max_uses: 1,
    });
    expect(limited.status).toBe(429);
    expect((await call("DELETE", "/runner-tokens/rt_01hxc1")).status).toBe(204);
    const tokens = (
      (await call("GET", "/runner-tokens")).data as {
        items: AdminRunnerToken[];
      }
    ).items;
    expect(tokens.find((t) => t.id === "rt_01hxc1")?.revoked).toBe(true);
    expect((await call("DELETE", "/runner-tokens/nope")).status).toBe(404);
  });

  it("раннер: пауза, ротация, отзыв", async () => {
    expect(
      (await call("PATCH", "/runners/rn_01hxb1", { paused: true })).status,
    ).toBe(204);
    expect((await call("PATCH", "/runners/rn_01hxb1", {})).status).toBe(422);
    const rotated = await call("POST", "/runners/rn_01hxb1/rotate-token");
    const body = rotated.data as { runner_token: string; runner: unknown };
    AdminRunnerSchema.parse(body.runner);
    expect(JSON.stringify((await call("GET", "/runners")).data)).not.toContain(
      body.runner_token,
    );
    expect((await call("DELETE", "/runners/rn_01hxb1")).status).toBe(204);
    expect((await call("POST", "/runners/rn_01hxb1/rotate-token")).status).toBe(
      404,
    );
  });

  it("очередь: фильтры по состоянию и виду, лимит и курсор", async () => {
    const queued = (await call("GET", "/queue", undefined, { state: "queued" }))
      .data as { items: { state: string }[]; next_cursor: string | null };
    expect(queued.items).toHaveLength(4);
    expect(queued.items.every((j) => j.state === "queued")).toBe(true);
    expect(queued.next_cursor).toBeNull();
    const kind = (
      await call("GET", "/queue", undefined, { kind: "pack.submission" })
    ).data as { items: unknown[] };
    expect(kind.items).toHaveLength(2);
    const page = (await call("GET", "/queue", undefined, { limit: "3" }))
      .data as { items: unknown[]; next_cursor: string | null };
    expect(page.items).toHaveLength(3);
    expect(page.next_cursor).not.toBeNull();
  });

  it("отмена: очередь и работа отменяются, завершённая задача остаётся как есть", async () => {
    const queued = await call("POST", "/queue/j_01hxd4/cancel");
    expect((queued.data as { state: string }).state).toBe("cancelled");
    const running = await call("POST", "/queue/j_01hxd1/cancel");
    expect((running.data as { state: string }).state).toBe("cancelled");
    const done = await call("POST", "/queue/j_01hxd8/cancel");
    expect(done.status).toBe(200);
    expect((done.data as { state: string }).state).toBe("succeeded");
    expect((await call("POST", "/queue/nope/cancel")).status).toBe(404);
    const summary = (await call("GET", "/queue/summary")).data as {
      by_state: { queued: number; running: number };
    };
    expect(summary.by_state.queued).toBe(3);
    expect(summary.by_state.running).toBe(2);
  });

  it("квоты: проверка границ и полная замена", async () => {
    const full = {
      user_concurrent: 3,
      org_concurrent: null,
      max_duration_s: 600,
    };
    expect(
      (await call("PUT", "/quotas", { ...full, user_concurrent: 0 })).status,
    ).toBe(422);
    expect(
      (await call("PUT", "/quotas", { ...full, max_duration_s: 5 })).status,
    ).toBe(422);
    const ok = await call("PUT", "/quotas", full);
    expect(AdminQuotasSchema.parse(ok.data)).toMatchObject(full);
    expect(
      AdminQuotasSchema.parse((await call("GET", "/quotas")).data),
    ).toMatchObject(full);
  });
});

describe("операционные разделы: экраны", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    await ensureAdminOpsLocales();
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("раннеры: состояние каждого считается по last_seen", async () => {
    render(wrap(<RunnersPage />));
    const status = async (id: string) =>
      (await screen.findByTestId(`runner-status-${id}`)).getAttribute(
        "data-status",
      );
    expect(await status("rn_01hxb1")).toBe("online");
    expect(await status("rn_01hxb3")).toBe("stale");
    expect(await status("rn_01hxb4")).toBe("paused");
    expect(await status("rn_01hxb5")).toBe("offline");
    expect(await status("rn_01hxb6")).toBe("revoked");
    expect(screen.getByTestId("runners-stat-online")).toHaveTextContent(
      /2\s*из 5/,
    );
    expect(screen.queryByTestId("runners-none-online")).toBeNull();
    // Занятость считается по выполняющимся задачам: у runner-1 две из двух.
    expect(
      await screen.findByText("2 из 2", {}, { timeout: 5000 }),
    ).toBeVisible();
    expect(screen.getByTestId("runners-stat-version")).toHaveTextContent(
      "1 раннер на старой версии",
    );
  }, 20_000);

  it("пауза и возврат раннера", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));
    await user.click(await screen.findByTestId("runner-actions-rn_01hxb1"));
    await user.click(await screen.findByTestId("runner-pause-rn_01hxb1"));
    await waitFor(() => {
      expect(screen.getByTestId("runner-status-rn_01hxb1")).toHaveAttribute(
        "data-status",
        "paused",
      );
    });
    await user.click(screen.getByTestId("runner-actions-rn_01hxb1"));
    expect(
      await screen.findByTestId("runner-pause-rn_01hxb1"),
    ).toHaveTextContent("Снять с паузы");
  }, 20_000);

  it("токен показывается один раз, вместе с командой запуска", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));
    await user.click(await screen.findByTestId("runner-token-create"));
    const form = await screen.findByTestId("token-create-form");
    await user.type(within(form).getByTestId("token-label"), "Стенд 2");
    await user.click(within(form).getByTestId("token-create-submit"));

    const secret = await screen.findByTestId("secret-once");
    const text = secret.textContent ?? "";
    expect(text).toMatch(/hse_rt_/);
    expect(text).toContain("HSE_RUNNER__API_URL=https://studio.example.org");
    expect(text).toContain("hse-doc-studio runner");
    // В списке токенов секрета нет, только название.
    expect(await screen.findByText("Стенд 2")).toBeVisible();
    expect(
      within(screen.getByTestId("runner-tokens")).queryByText(/hse_rt_/),
    ).toBeNull();

    // Закрытие без копирования просит подтвердить; после подтверждения секрета нигде нет.
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByTestId("secret-once")).toBeNull();
    });
    expect(screen.queryByText(/hse_rt_/)).toBeNull();
    await user.click(screen.getByTestId("runner-token-create"));
    expect(await screen.findByTestId("token-create-form")).toBeVisible();
    expect(screen.queryByText(/hse_rt_/)).toBeNull();
  }, 20_000);

  it("токен: неверное число подключений и отказ по частоте", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));
    await user.click(await screen.findByTestId("runner-token-create"));
    const form = await screen.findByTestId("token-create-form");
    const uses = within(form).getByTestId("token-max-uses");
    await user.clear(uses);
    await user.type(uses, "0");
    await user.click(within(form).getByTestId("token-create-submit"));
    expect(
      await within(form).findByText("Введите целое число от 1 до 100."),
    ).toBeVisible();
    await user.clear(uses);
    await user.type(uses, "2");
    await user.type(within(form).getByTestId("token-label"), "limit");
    await user.click(within(form).getByTestId("token-create-submit"));
    expect(
      await within(form).findByText(/Слишком много запросов/),
    ).toBeVisible();
  }, 20_000);

  it("токен: отзыв просит подтверждения", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));
    // Отзыв в меню «⋯», как у раннеров: состояния токенов стоят ровно.
    await user.click(await screen.findByTestId("token-actions-rt_01hxc1"));
    await user.click(await screen.findByTestId("token-revoke-rt_01hxc1"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Сервер в аудитории 305/)).toBeVisible();
    await user.click(within(dialog).getByTestId("token-revoke-dialog-confirm"));
    await waitFor(() => {
      expect(screen.getByTestId("token-rt_01hxc1")).toHaveAttribute(
        "data-status",
        "revoked",
      );
    });
  }, 20_000);

  it("новый токен раннера: подтверждение, затем секрет с командой", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));
    await user.click(await screen.findByTestId("runner-actions-rn_01hxb2"));
    await user.click(await screen.findByTestId("runner-rotate-rn_01hxb2"));
    const confirm = await screen.findByTestId("rotate-dialog");
    expect(within(confirm).getByText(/перестанет действовать/)).toBeVisible();
    await user.click(screen.getByTestId("rotate-dialog-confirm"));
    const secret = await screen.findByTestId("secret-once");
    expect(secret.textContent).toMatch(/hse_rn_/);
    expect(secret.textContent).toContain("HSE_RUNNER__TOKEN=hse_rn_");
  }, 20_000);

  it("отзыв раннера требует ввести его имя", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));
    await user.click(await screen.findByTestId("runner-actions-rn_01hxb5"));
    await user.click(await screen.findByTestId("runner-revoke-rn_01hxb5"));
    const confirmButton = await screen.findByRole("button", {
      name: "Отозвать",
    });
    expect(confirmButton).toBeDisabled();
    await user.type(screen.getByRole("textbox"), "runner-5");
    await user.click(confirmButton);
    await waitFor(() => {
      expect(screen.getByTestId("runner-status-rn_01hxb5")).toHaveAttribute(
        "data-status",
        "revoked",
      );
    });
  }, 20_000);

  it("раннеры не в сети: предупреждение и долгая очередь", async () => {
    activateServerScenario("ops_runners_offline");
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));
    expect(await screen.findByTestId("runners-none-online")).toBeVisible();
    await user.click(screen.getByTestId("ops-tab-queue"));
    await waitFor(() => {
      expect(screen.getByTestId("queue-stat-queued")).toHaveTextContent(
        /В очереди\s*4/,
      );
    });
    // Самая старая задача ждёт больше двух минут: время подсвечено.
    expect(await screen.findByTestId("job-wait-j_01hxe1")).toHaveTextContent(
      "21 мин",
    );
  }, 20_000);

  it("чистая установка: одно пустое состояние, а не два", async () => {
    activateServerScenario("ops_fresh");
    render(wrap(<RunnersPage />));
    expect(await screen.findByTestId("runners-empty")).toBeVisible();
    expect(screen.getByTestId("runners-empty-create")).toBeVisible();
    // Пустой блок токенов повторял бы тот же совет: его нет.
    expect(screen.queryByTestId("runner-tokens")).toBeNull();
  }, 20_000);

  it("очередь: сводка, поиск и отмена с подтверждением", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage initialTab="queue" />));
    await waitFor(() => {
      expect(screen.getByTestId("queue-stat-queued")).toHaveTextContent(
        /В очереди\s*4/,
      );
    });
    expect(screen.getByTestId("queue-stat-running")).toHaveTextContent("3");
    expect(screen.getByTestId("queue-class-interactive")).toBeVisible();

    await user.click(await screen.findByTestId("job-cancel-j_01hxd4"));
    const dialog = await screen.findByTestId("cancel-dialog");
    expect(within(dialog).getByText(/будет остановлена/)).toBeVisible();
    await user.click(screen.getByTestId("cancel-dialog-confirm"));
    await waitFor(() => {
      expect(screen.getByTestId("job-status-j_01hxd4")).toHaveTextContent(
        "Отменена",
      );
    });
    expect(screen.queryByTestId("job-cancel-j_01hxd4")).toBeNull();
  }, 20_000);

  it("очередь: отмена выполняющейся задачи предупреждает о результате", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage initialTab="queue" />));
    await user.click(await screen.findByTestId("job-cancel-j_01hxd1"));
    expect(await screen.findByText(/результат не сохранится/)).toBeVisible();
  }, 20_000);

  it("очередь: подробности задачи показывают ошибку без путей", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage initialTab="queue" />));
    await user.click(await screen.findByTestId("job-status-j_01hxd9"));
    const detail = await screen.findByTestId("job-detail");
    // Код ошибки переведён в человеческий текст, сам код остаётся мелко для журнала.
    expect(within(detail).getByTestId("job-error")).toHaveTextContent(
      "Раннер вернул повреждённый результат",
    );
    expect(within(detail).getByTestId("job-error")).toHaveTextContent(
      "artifact_invalid",
    );
    expect(detail.textContent).toContain("runner-2");
    expect(detail.textContent).toContain("1 из 3");
  }, 20_000);

  it("очередь: люди по именам, удалённый без идентификатора", async () => {
    render(wrap(<RunnersPage initialTab="queue" />));
    expect(await screen.findAllByText("Мария Келлер")).not.toHaveLength(0);
    // Имя приходит в строке очереди сразу, почта дочитывается по человеку.
    expect(
      await screen.findAllByText("maria.keller@example.org"),
    ).not.toHaveLength(0);
    expect(await screen.findByText("Удалённый пользователь")).toBeVisible();
    expect(screen.queryByText(/u_01hx/)).toBeNull();
    // Счётчики состояний у фильтров приходят из сводки.
    expect(
      screen.getByRole("button", { name: /Выполняется\s*3/ }),
    ).toBeVisible();
  }, 20_000);

  it("очередь: поиск по человеку", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage initialTab="queue" />));
    await screen.findByTestId("job-status-j_01hxd1");
    await screen.findAllByText("Дарья Лис");
    await user.type(
      screen.getByRole("searchbox", {
        name: "Найти по человеку, проекту или раннеру",
      }),
      "Лис",
    );
    await waitFor(() => {
      expect(screen.queryByTestId("job-status-j_01hxd1")).toBeNull();
    });
    expect(screen.getByTestId("job-status-j_01hxd3")).toBeVisible();
  }, 20_000);

  it("квоты: сохранение, проверка границ", async () => {
    const user = userEvent.setup();
    render(wrap(<QuotasPage />));
    const concurrent = await screen.findByTestId("quota-concurrent");
    // Панель сохранения появляется только с правками.
    expect(screen.queryByTestId("quotas-save")).toBeNull();
    await user.clear(concurrent);
    await user.type(concurrent, "0");
    expect(screen.getByTestId("quotas")).toHaveTextContent(
      "1 несохранённое изменение",
    );
    await user.click(screen.getByTestId("quotas-save"));
    expect(
      await screen.findByText("Целое число от 1 до 1000 или пусто."),
    ).toBeVisible();
    await user.clear(concurrent);
    await user.type(concurrent, "3");
    await user.click(screen.getByTestId("quotas-save"));
    expect(await screen.findByTestId("quotas-saved")).toBeVisible();
    expect(screen.getByTestId("quota-concurrent")).toHaveValue(3);
    // Пустое поле снимает предел.
    await user.clear(screen.getByTestId("quota-org-concurrent"));
    await user.click(screen.getByTestId("quotas-save"));
    await waitFor(() => {
      expect(screen.getByTestId("quota-org-concurrent")).toHaveValue(null);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("quotas-save")).toBeNull();
    });
  }, 20_000);

  it("квоты: «Отменить» возвращает сохранённые значения", async () => {
    const user = userEvent.setup();
    render(wrap(<QuotasPage />));
    const duration = await screen.findByTestId("quota-duration");
    await user.clear(duration);
    await user.type(duration, "30");
    await user.click(screen.getByTestId("quotas-discard"));
    expect(screen.getByTestId("quota-duration")).toHaveValue(10);
    expect(screen.queryByTestId("quotas")).toBeNull();
    expect(screen.getByTestId("quotas-explain")).toHaveTextContent(
      "ждёт, а не отклоняется",
    );
  }, 20_000);

  it("сервисы: мало раннеров в сети, и сводка говорит о перебоях", async () => {
    const user = userEvent.setup();
    render(wrap(<ServicesPage />));
    expect(await screen.findByTestId("service-runners")).toBeVisible();
    // У здоровых сервисов нет строки причины.
    expect(screen.queryByTestId("service-detail-database")).toBeNull();
    expect(screen.getByTestId("service-runners")).toHaveTextContent("2 из 5");
    // Меньше половины раннеров в сети: карточка предупреждает, и сводка над
    // карточками говорит то же самое, а не «всё работает».
    expect(screen.getByTestId("service-runners")).toHaveTextContent(
      "Часть не на связи",
    );
    expect(screen.getByTestId("services-summary")).toHaveTextContent(
      "Перебои у 1 сервиса",
    );
    expect(screen.getByTestId("services-summary")).toHaveTextContent("Раннеры");
    await user.click(screen.getByTestId("services-refresh"));
    expect(await screen.findByTestId("service-database")).toBeVisible();
  }, 20_000);

  it("сервисы падают: причины и сводка об отказе", async () => {
    activateServerScenario("ops_services_degraded");
    render(wrap(<ServicesPage />));
    expect(await screen.findByTestId("service-s3")).toHaveAttribute(
      "data-status",
      "down",
    );
    expect(screen.getByTestId("service-detail-s3")).toHaveTextContent(
      "Не ответил вовремя",
    );
    // Код причины не на виду: он в подсказке у человеческой причины.
    expect(
      screen.getByTestId("service-detail-s3").querySelector("[data-code]"),
    ).toHaveAttribute("data-code", "timeout");
    expect(screen.getByTestId("services-off")).toHaveTextContent("Почта");
    expect(screen.getByTestId("service-languagetool")).toHaveAttribute(
      "data-status",
      "down",
    );
    expect(screen.getByTestId("services-summary")).toHaveTextContent(
      "Не работают 3 сервиса",
    );
  }, 20_000);

  it("хранилище: владельцы по убыванию, места достаточно", async () => {
    render(wrap(<StoragePage />));
    const top = await screen.findByTestId("owner-u_01hx7k2c1d");
    expect(top).toHaveTextContent("Мария Келлер");
    expect(
      await within(top).findByText("maria.keller@example.org"),
    ).toBeVisible();
    expect(screen.getByTestId("storage-total")).toHaveTextContent("38");
    expect(screen.getByTestId("storage-free")).toHaveTextContent("86 ГБ");
    expect(screen.getByTestId("storage-disk")).toHaveTextContent(
      "занято 114 ГБ из 200 ГБ",
    );
    expect(screen.queryByTestId("storage-low")).toBeNull();
    expect(screen.getByTestId("storage-note")).toHaveTextContent("без обхода");
  }, 20_000);

  it("хранилище: места мало, предупреждение", async () => {
    activateServerScenario("ops_services_degraded");
    render(wrap(<StoragePage />));
    expect(await screen.findByTestId("storage-low")).toHaveTextContent(
      "2,4 ГБ",
    );
  }, 20_000);

  it("английский интерфейс", async () => {
    await i18n.changeLanguage("en");
    render(wrap(<RunnersPage />));
    expect(await screen.findByText("Registration tokens")).toBeVisible();
    expect(
      await screen.findByTestId("runner-status-rn_01hxb1"),
    ).toHaveTextContent("Online");
    await i18n.changeLanguage("ru");
  }, 20_000);

  it("локаль подключается один раз", async () => {
    const first = ensureAdminOpsLocales();
    expect(ensureAdminOpsLocales()).toBe(first);
    await first;
    expect(i18n.hasResourceBundle("ru", "adminOps")).toBe(true);
    expect(i18n.hasResourceBundle("en", "adminOps")).toBe(true);
  });
});
