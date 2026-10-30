import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { z } from "zod";
import { i18n } from "@shared/lib";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import {
  AdminJobPageSchema,
  AdminRunnerSchema,
  type AdminRunner,
} from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { serverAdminDemoRoutes } from "@/app/demo/server/routes";
import { jobWhere } from "./lib/jobs";
import { ensureAdminOpsLocales } from "./lib/locales";
import { RunnersPage } from "./index";
import { personalStatus } from "./lib/personalStatus";
import { PersonalRunnersView } from "./ui/PersonalRunnersView";

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

const NOW = Date.parse("2026-10-30T10:00:00Z");
const PERSONAL: AdminRunner = {
  id: "p1",
  name: "MacBook Анны",
  status: "online",
  tags: ["tex"],
  concurrency: 1,
  resource_class: "standard",
  version: "0.3.0",
  created_at: "2026-10-28T10:00:00Z",
  last_seen_at: "2026-10-30T09:59:50Z",
  paused: false,
  revoked: false,
  owner_kind: "user",
  owner: {
    id: "u1",
    name: "Анна Петрова",
    email: "anna.petrova@example.org",
  },
  host_kind: "desktop",
  ai_endpoints: ["ollama"],
  last_seen_ip: "203.0.113.7",
};
const noop = () => undefined;

describe("админка: личные раннеры", () => {
  beforeAll(async () => {
    installServerDemo();
    await ensureAdminOpsLocales();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("admin_personal_runners");
  });
  afterEach(cleanup);

  it("состояние: выключенные админом и пауза важнее тишины", () => {
    expect(personalStatus(PERSONAL, NOW)).toBe("online");
    expect(personalStatus({ ...PERSONAL, status: "disabled" }, NOW)).toBe(
      "disabled",
    );
    expect(personalStatus({ ...PERSONAL, paused: true }, NOW)).toBe("paused");
  });

  it("где задача: общий, личный, ИИ, ждёт личный", () => {
    const base = {
      status: "running" as const,
      route: null,
      runner_scope: null,
    };
    expect(jobWhere({ ...base, kind: "ai.relay" })).toBe("ai");
    expect(
      jobWhere({ ...base, kind: "compile", runner_scope: "personal" }),
    ).toBe("personal");
    expect(
      jobWhere({
        kind: "compile",
        status: "queued",
        route: "personal_first",
        runner_scope: null,
      }),
    ).toBe("waiting");
    // Старый сервер без полей маршрута: идущая задача на общем раннере.
    expect(jobWhere({ kind: "compile", status: "running" })).toBe("shared");
  });

  it("вид: владелец, ИИ-адреса, баннер выключения", () => {
    render(
      wrap(
        <PersonalRunnersView
          status="ready"
          runners={[PERSONAL]}
          enabled={false}
          now={NOW}
          onTogglePause={noop}
          onRevoke={noop}
        />,
      ),
    );
    expect(screen.getByTestId("admin-runner-owner-p1")).toHaveTextContent(
      "Анна Петрова",
    );
    expect(screen.getByText("ollama")).toBeInTheDocument();
    expect(
      screen.getByTestId("admin-personal-runners-disabled"),
    ).toBeInTheDocument();
  });

  it("вид: пусто", () => {
    render(
      wrap(
        <PersonalRunnersView
          status="ready"
          runners={[]}
          enabled
          now={NOW}
          onTogglePause={noop}
          onRevoke={noop}
        />,
      ),
    );
    expect(
      screen.getByTestId("admin-personal-runners-empty"),
    ).toHaveTextContent("Личных раннеров нет");
  });

  it("демо: список с владельцами, смена токена личного 403, пауза и отзыв", async () => {
    const all = z
      .array(AdminRunnerSchema)
      .parse((await call("GET", "/runners")).data);
    const personal = all.filter((r) => r.owner_kind === "user");
    expect(personal.length).toBeGreaterThan(0);
    expect(personal.every((r) => r.owner !== null)).toBe(true);
    const onlyUsers = z
      .array(AdminRunnerSchema)
      .parse(
        (await call("GET", "/runners", undefined, { owner_kind: "user" })).data,
      );
    expect(onlyUsers.every((r) => r.owner_kind === "user")).toBe(true);

    const id = "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b";
    const rotate = await call("POST", `/runners/${id}/rotate-token`);
    expect(rotate.status).toBe(403);
    expect(
      (await call("PATCH", `/runners/${id}`, { paused: true })).status,
    ).toBe(204);
    expect((await call("DELETE", `/runners/${id}`)).status).toBe(204);
  });

  it("демо: очередь знает, где идут задачи, и фильтрует по месту", async () => {
    const page = AdminJobPageSchema.parse(
      (await call("GET", "/queue", undefined, { runner_scope: "personal" }))
        .data,
    );
    expect(page.items.length).toBeGreaterThan(0);
    expect(page.items.every((j) => j.runner_scope === "personal")).toBe(true);
    expect(page.items.some((j) => j.kind === "ai.relay")).toBe(true);
  });

  it("раздел «Раннеры»: личные отдельно от раннеров установки", async () => {
    render(wrap(<RunnersPage />));
    const section = await screen.findByTestId("admin-personal-runners");
    await waitFor(() => {
      expect(section).toHaveTextContent("Анна Петрова");
    });
    expect(screen.getByTestId("runners-view")).not.toHaveTextContent(
      "MacBook Анны",
    );
  });

  it("очередь: колонка «Где» и плитка личных раннеров", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage initialTab="queue" />));
    expect(await screen.findByTestId("queue-where-j_01hxp1")).toHaveAttribute(
      "data-where",
      "personal",
    );
    expect(screen.getByTestId("queue-where-j_01hxp3")).toHaveAttribute(
      "data-where",
      "ai",
    );
    await waitFor(() => {
      expect(screen.getByTestId("queue-stat-personal")).toHaveTextContent("2");
    });
    await user.click(screen.getByRole("button", { name: /Личный/ }));
    await waitFor(() => {
      expect(screen.queryByTestId("queue-where-j_01hxd2")).toBeNull();
    });
  });
});
