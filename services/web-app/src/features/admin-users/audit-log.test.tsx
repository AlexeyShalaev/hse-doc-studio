import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { i18n } from "@shared/lib";
import type { AdminAuditEvent } from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { auditTarget, daysAgo, groupByDay } from "./lib/auditFormat";
import { ensureAdminUsersLocales } from "./lib/locales";
import { AuditLog } from "./index";

// Журнал аудита поверх демо-мира: люди по именам, дни, подробности по клику.

const mount = () =>
  render(
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
        <AuditLog />
      </QueryClientProvider>
    </I18nextProvider>,
  );

const rowOf = async (text: string): Promise<HTMLElement> => {
  const label = (await screen.findAllByText(text))[0];
  const row = label?.closest("li");
  if (!row) throw new Error(`no audit row with ${text}`);
  return row;
};

describe("журнал аудита", () => {
  beforeAll(async () => {
    installServerDemo();
    await ensureAdminUsersLocales();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("люди и цели по именам, без служебных идентификаторов", async () => {
    mount();
    const row = await rowOf("Аккаунт одобрен");
    expect(row).toHaveTextContent("Мария Келлер");
    expect(row).toHaveTextContent("Иван Сидоров");
    const list = screen.getAllByRole("list", { name: "Журнал событий" });
    for (const day of list) expect(day.textContent).not.toMatch(/u_01hx/);
  });

  it("события разложены по дням", async () => {
    mount();
    expect(await screen.findByText("Сегодня")).toBeVisible();
    expect(screen.getByText("Вчера")).toBeVisible();
    expect(screen.getByRole("region", { name: "Сегодня" })).toHaveTextContent(
      /\d+ событи/,
    );
  });

  it("неудачный вход от системы, подробности раскрываются по клику", async () => {
    const user = userEvent.setup();
    mount();
    const failed = await rowOf("Неудачная попытка входа");
    expect(failed).toHaveTextContent("Система");
    expect(failed).toHaveTextContent("Причина: неверный пароль");

    const invite = await rowOf("Приглашение создано");
    const toggle = within(invite).getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    // Код события виден только в подробностях, моноширинным.
    expect(within(invite).getByText("invite.create")).toHaveClass("mono");
    expect(invite).toHaveTextContent("Срок7 дней");
    await user.click(toggle);
    expect(within(invite).queryByText("invite.create")).toBeNull();
  });

  it("пустой журнал на свежей установке", async () => {
    activateServerScenario("install_fresh");
    mount();
    expect(await screen.findByTestId("audit-empty")).toHaveTextContent(
      "Записей пока нет",
    );
  });

  it("ничего не нашли: кнопка сбрасывает фильтры", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText("Сегодня");
    await user.type(screen.getByRole("searchbox"), "нет-такого");
    const empty = await screen.findByTestId("audit-empty");
    await user.click(
      within(empty).getByRole("button", { name: "Сбросить фильтры" }),
    );
    expect(await screen.findByText("Сегодня")).toBeVisible();
  });

  it("без прав показывает ошибку с повтором", async () => {
    activateServerScenario("student_ready");
    mount();
    const failed = await screen.findByTestId("audit-failed");
    expect(failed).toHaveTextContent("Не удалось загрузить журнал");
    expect(
      within(failed).getByRole("button", { name: "Повторить" }),
    ).toBeVisible();
  });

  it("английский интерфейс", async () => {
    await i18n.changeLanguage("en");
    mount();
    expect(await screen.findByText("Today")).toBeVisible();
    expect(await rowOf("Account approved")).toHaveTextContent("Мария Келлер");
  });
});

describe("разбор журнала", () => {
  const event = (
    patch: Partial<AdminAuditEvent> & Pick<AdminAuditEvent, "at">,
  ): AdminAuditEvent => ({
    id: 1,
    action: "auth.login",
    actor_id: null,
    actor: null,
    target: null,
    target_label: null,
    details: {},
    ...patch,
  });

  it("цель: человек, понятное поле или ничего вместо id", () => {
    const people = new Map([
      [
        "u_1abcdef",
        {
          id: "u_1abcdef",
          name: "Анна",
          email: "a@example.org",
          status: "active" as const,
          is_instance_admin: false,
          created_at: "2026-01-01T00:00:00Z",
          last_login_at: null,
          project_count: 0,
        },
      ],
    ]);
    const at = "2026-10-30T10:00:00Z";
    expect(
      auditTarget(event({ at, target: "u_1abcdef" }), people),
    ).toMatchObject({ kind: "person" });
    expect(
      auditTarget(
        event({ at, target: "org_01hxp3", details: { slug: "x" } }),
        people,
      ),
    ).toEqual({ kind: "text", text: "x", key: "slug" });
    expect(auditTarget(event({ at, target: "rn_01hxb4" }), people)).toBeNull();
  });

  it("дни: подряд идущие события одного дня вместе", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 30, 12));
    const days = groupByDay([
      event({ at: new Date(2026, 9, 30, 11).toISOString() }),
      event({ at: new Date(2026, 9, 30, 9).toISOString() }),
      event({ at: new Date(2026, 9, 29, 22).toISOString() }),
    ]);
    expect(days.map((d) => d.events.length)).toEqual([2, 1]);
    expect(days.map((d) => daysAgo(d.key, new Date()))).toEqual([0, 1]);
    vi.useRealTimers();
  });
});
