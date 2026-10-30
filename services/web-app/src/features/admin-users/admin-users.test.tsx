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
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import {
  AdminAuditPageSchema,
  AdminInvitationCreatedSchema,
  AdminInvitationPageSchema,
  AdminUserPageSchema,
} from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { serverAdminDemoRoutes } from "@/app/demo/server/routes";
import { ensureAdminUsersLocales } from "./lib/locales";
import { AdminUsers, AuditLog } from "./index";

// Люди в админке поверх демо-транспорта: те же запросы, что уйдут настоящему бэкенду,
// и ответы, проходящие те же строгие схемы.

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
      {node}
    </QueryClientProvider>
  </I18nextProvider>
);

const router = createDemoRouter(serverAdminDemoRoutes);
const call = async (
  method: DemoRequest["method"],
  path: string,
  body?: unknown,
  query: Record<string, string> = {},
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

describe("люди в админке: демо-API", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(() => {
    activateServerScenario("admin_ready");
  });

  it("ответы проходят схемы контракта", async () => {
    AdminUserPageSchema.parse((await call("GET", "/users")).data);
    AdminUserPageSchema.parse((await call("GET", "/approvals")).data);
    AdminInvitationPageSchema.parse((await call("GET", "/invitations")).data);
    AdminAuditPageSchema.parse((await call("GET", "/audit")).data);
    AdminInvitationCreatedSchema.parse(
      (await call("POST", "/invitations", { email: null, ttl_days: 7 })).data,
    );
  });

  it("последнего администратора не отключить и не понизить", async () => {
    const own = "u_01hx7k1a0b";
    expect((await call("POST", `/users/${own}/disable`)).status).toBe(409);
    expect(
      (await call("PATCH", `/users/${own}`, { is_instance_admin: false }))
        .status,
    ).toBe(409);
  });

  it("удалить можно только отключённый аккаунт без проектов", async () => {
    expect((await call("DELETE", "/users/u_01hx7k2c1d")).status).toBe(409);
    expect((await call("DELETE", "/users/u_01hx7k6k5l")).status).toBe(204);
  });

  it("неверная почта приглашения даёт 422", async () => {
    expect(
      (await call("POST", "/invitations", { email: "не-адрес", ttl_days: 7 }))
        .status,
    ).toBe(422);
  });
});

describe("люди в админке: экраны", () => {
  beforeAll(async () => {
    installServerDemo();
    await i18n.changeLanguage("ru");
    await ensureAdminUsersLocales();
  });
  beforeEach(() => {
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("список людей: состояния, поиск и себя отключить нельзя", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    expect(await screen.findByText("Мария Келлер")).toBeVisible();
    expect(screen.getByTestId("status-disabled")).toBeVisible();
    expect(screen.getByText("вы")).toBeVisible();
    await user.type(screen.getByRole("searchbox"), "келлер");
    await waitFor(() => {
      expect(screen.queryByText("Пётр Орлов")).toBeNull();
    });
    await user.clear(screen.getByRole("searchbox"));
    await user.type(screen.getByRole("searchbox"), "никого-нет");
    expect(await screen.findByText("Никого не нашли")).toBeVisible();
  });

  it("отключение требует подтверждения, ссылка сброса показывается на экране", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    await screen.findByText("Мария Келлер");
    await user.click(screen.getByTestId("user-actions-u_01hx7k2c1d"));
    await user.click(await screen.findByTestId("user-disable-u_01hx7k2c1d"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Отключить аккаунт?")).toBeVisible();
    await user.click(within(dialog).getByTestId("user-confirm"));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    await waitFor(() => {
      expect(screen.getAllByTestId("status-disabled")).toHaveLength(2);
    });

    await user.click(screen.getByTestId("user-actions-u_01hx7k3e2f"));
    await user.click(await screen.findByTestId("user-reset-u_01hx7k3e2f"));
    await user.click(
      within(await screen.findByRole("dialog")).getByTestId("user-confirm"),
    );
    expect(await screen.findByTestId("link-delivery")).toBeVisible();
  });

  it("назначение администратором меняет действие в меню", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    await screen.findByText("Мария Келлер");
    await user.click(screen.getByTestId("user-actions-u_01hx7k2c1d"));
    await user.click(await screen.findByTestId("user-admin-u_01hx7k2c1d"));
    await user.click(
      within(await screen.findByRole("dialog")).getByTestId("user-confirm"),
    );
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    // Мария стала администратором: в списке две плашки роли.
    await waitFor(() => {
      expect(screen.getAllByText("Администратор")).toHaveLength(2);
    });
  });

  it("приглашение: ссылка один раз, неверная почта, отзыв", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    await user.click(await screen.findByTestId("users-tab-invitations"));
    expect(await screen.findByText("new.student@example.org")).toBeVisible();

    await user.type(screen.getByTestId("invite-email"), "не-адрес");
    await user.click(screen.getByTestId("invite-submit"));
    expect(await screen.findByText("Введите адрес почты.")).toBeVisible();

    await user.clear(screen.getByTestId("invite-email"));
    await user.type(screen.getByTestId("invite-email"), "fresh@example.org");
    await user.click(screen.getByTestId("invite-submit"));
    expect(await screen.findByTestId("link-delivery")).toBeVisible();
    expect(await screen.findByText("fresh@example.org")).toBeVisible();

    await user.click(screen.getByTestId("invite-revoke-inv_01"));
    await waitFor(() => {
      expect(screen.queryByText("new.student@example.org")).toBeNull();
    });
  });

  it("одобрения: счётчик на вкладке и решение", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    await user.click(await screen.findByTestId("users-tab-approvals"));
    expect(await screen.findByText("Анна Волкова")).toBeVisible();
    await user.click(screen.getByTestId("approve-u_01hx7k4g3h"));
    expect(await screen.findByText("Очередь пуста")).toBeVisible();
  });

  it("аудит: подписи действий, фильтр и подгрузка", async () => {
    const user = userEvent.setup();
    render(wrap(<AuditLog />));
    expect((await screen.findAllByText("Вход")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Аккаунт одобрен").length).toBeGreaterThan(0);
    await user.click(screen.getByTestId("audit-more"));
    await waitFor(() => {
      expect(screen.getAllByTestId(/^audit-\d+$/).length).toBeGreaterThan(25);
    });
    await user.click(screen.getByRole("button", { name: "Люди" }));
    await waitFor(() => {
      expect(screen.queryByText("Вход")).toBeNull();
    });
  });

  it("аудит: поиск по загруженным записям и пустой результат", async () => {
    const user = userEvent.setup();
    render(wrap(<AuditLog />));
    await screen.findAllByText("Вход");
    await user.type(screen.getByRole("searchbox"), "нет-такого");
    expect(await screen.findByText("Ничего не нашли")).toBeVisible();
    await user.clear(screen.getByRole("searchbox"));
    await user.type(screen.getByRole("searchbox"), "аккаунт одобрен");
    await waitFor(() => {
      expect(screen.getAllByText("Аккаунт одобрен").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Вход")).toBeNull();
  });

  it("английский интерфейс", async () => {
    await i18n.changeLanguage("en");
    render(wrap(<AdminUsers />));
    expect(await screen.findByText("Awaiting approval")).toBeVisible();
    await i18n.changeLanguage("ru");
  });
});
