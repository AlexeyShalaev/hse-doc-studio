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
import { detailText } from "./lib/format";
import { ensureAdminUsersLocales } from "./lib/locales";
import { AdminUsers } from "./index";

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

    await user.click(screen.getByTestId("invite-actions-inv_01"));
    await user.click(await screen.findByTestId("invite-revoke-inv_01"));
    await waitFor(() => {
      expect(screen.queryByText("new.student@example.org")).toBeNull();
    });
  });

  it("одобрения: счётчик на вкладке, решение в строке и пачкой", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    const tab = await screen.findByTestId("users-tab-approvals");
    await waitFor(() => {
      expect(tab).toHaveTextContent("3");
    });
    await user.click(tab);
    expect(await screen.findByText("3 заявки ждут решения")).toBeVisible();
    await user.click(screen.getByTestId("approve-u_01hx7k4g3h"));
    await waitFor(() => {
      expect(screen.queryByText("Анна Волкова")).toBeNull();
    });
    expect(screen.getByText("2 заявки ждут решения")).toBeVisible();

    // Отмеченная заявка одна: кнопка пачки одобряет только её.
    await user.click(
      screen.getByRole("checkbox", { name: "Выбрать Артём Ковалёв" }),
    );
    expect(screen.getByTestId("approve-bulk")).toHaveTextContent(
      "Одобрить выбранные (1)",
    );
    await user.click(screen.getByTestId("approve-bulk"));
    await waitFor(() => {
      expect(screen.queryByText("Артём Ковалёв")).toBeNull();
    });
    await user.click(screen.getByTestId("approve-bulk"));
    expect(await screen.findByText("Очередь пуста")).toBeVisible();
  });

  it("карточка человека: сведения и действия по клику на строку", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    await user.click(await screen.findByText("Мария Келлер"));
    const drawer = await screen.findByTestId("person-drawer");
    expect(within(drawer).getByText("maria.keller@example.org")).toBeVisible();
    expect(within(drawer).getByText("Зарегистрирован")).toBeVisible();
    await user.click(within(drawer).getByTestId("drawer-revokeSessions"));
    const confirm = await screen.findByRole("dialog", {
      name: "Завершить все входы?",
    });
    await user.click(within(confirm).getByTestId("user-confirm"));
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "Завершить все входы?" }),
      ).toBeNull();
    });
  });

  it("свой аккаунт: в карточке нельзя отключить себя и снять свои права", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    await user.click(await screen.findByText("Иван Сидоров"));
    const drawer = await screen.findByTestId("person-drawer");
    expect(within(drawer).getByTestId("drawer-disable")).toBeDisabled();
    expect(within(drawer).getByTestId("drawer-revokeAdmin")).toBeDisabled();
    expect(within(drawer).getByTestId("drawer-resetLink")).toBeEnabled();
  });

  it("фильтр по состоянию показывает число людей на чипе", async () => {
    const user = userEvent.setup();
    render(wrap(<AdminUsers />));
    await screen.findByText("Мария Келлер");
    const chip = await screen.findByRole("button", { name: /Ждёт одобрения/ });
    await waitFor(() => {
      expect(chip).toHaveTextContent("3");
    });
    await user.click(chip);
    await waitFor(() => {
      expect(screen.queryByText("Мария Келлер")).toBeNull();
    });
    expect(screen.getByText("Ксения Лебедева")).toBeVisible();
  });

  it("не админ установки видит запрет, а не ошибку", async () => {
    activateServerScenario("org_admin");
    render(wrap(<AdminUsers />));
    expect(await screen.findByTestId("users-forbidden")).toBeVisible();
    expect(screen.queryByTestId("users-invite")).toBeNull();
  });

  it("английский интерфейс", async () => {
    await i18n.changeLanguage("en");
    render(wrap(<AdminUsers />));
    expect(
      (await screen.findAllByText("Awaiting approval")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Invite" })).toBeVisible();
    await i18n.changeLanguage("ru");
  });
});

describe("подробности журнала", () => {
  it("вложенные значения читаются как ключ=значение, а не как JSON", () => {
    expect(detailText({ user_concurrent: 1, max_duration_s: null })).toBe(
      "user_concurrent=1, max_duration_s=∅",
    );
    expect(detailText(["a", "b"])).toBe("a, b");
    expect(detailText("plain")).toBe("plain");
    expect(detailText(null)).toBe("");
  });
});
