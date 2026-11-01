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
import { MemoryRouter, useLocation } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { adminClient } from "@shared/api";
import { i18n } from "@shared/lib";
import type { AdminAuditEvent } from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import {
  auditTarget,
  daysAgo,
  groupByDay,
  isPseudonym,
} from "./lib/auditFormat";
import { ensureAdminUsersLocales } from "./lib/locales";
import { AuditLog } from "./index";

// Журнал аудита поверх демо-мира: люди по именам из самих строк, дни,
// подробности по клику; поиск, разделы, человек и период уходят на сервер.

// Адрес страницы: состояние журнала живёт в нём.
const Probe = () => (
  <output data-testid="location">{useLocation().search}</output>
);
const location = (): string => screen.getByTestId("location").textContent;

const mount = (entry = "/admin/audit") =>
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
        <MemoryRouter initialEntries={[entry]}>
          <AuditLog />
          <Probe />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

// Поиск ждёт паузу в наборе и ответ демо-сервера: на загруженной машине это
// дольше секунды по умолчанию.
const SLOW = { timeout: 5000 };

const rowOf = async (text: string): Promise<HTMLElement> => {
  const label = (await screen.findAllByText(text, {}, SLOW))[0];
  const row = label?.closest("li");
  if (!row) throw new Error(`no audit row with ${text}`);
  return row;
};

const rows = () => screen.queryAllByTestId(/^audit-\d+$/);

/** Кнопка строки, которая раскрывает подробности. */
const toggleOf = (row: HTMLElement): HTMLElement => {
  const toggle = within(row).getAllByRole("button")[0];
  if (!toggle) throw new Error("no toggle");
  return toggle;
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
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("люди и цели по именам, без служебных идентификаторов", async () => {
    mount();
    const row = await rowOf("Аккаунт одобрен");
    expect(row).toHaveTextContent("Мария Келлер");
    expect(row).toHaveTextContent("Иван Сидоров");
    const list = screen.getAllByRole("list", { name: "Журнал событий" });
    for (const day of list) expect(day.textContent).not.toMatch(/u_01hx/);
  });

  it("имена приходят в строках: справочник людей не запрашивается", async () => {
    const get = vi.spyOn(adminClient, "get");
    mount();
    await rowOf("Аккаунт одобрен");
    const urls = get.mock.calls.map(([url]) => url);
    expect(urls).toContain("/audit");
    expect(urls).not.toContain("/users");
    expect(urls).not.toContain("/approvals");
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
    const toggle = toggleOf(invite);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    // Код события виден только в подробностях, моноширинным.
    expect(within(invite).getByText("invite.create")).toHaveClass("mono");
    expect(invite).toHaveTextContent("Срок7 дней");
    await user.click(toggle);
    expect(within(invite).queryByText("invite.create")).toBeNull();
  });

  it("поиск уходит на сервер и попадает в адрес", async () => {
    const user = userEvent.setup();
    const get = vi.spyOn(adminClient, "get");
    mount();
    await screen.findByText("Сегодня");
    await user.type(screen.getByRole("searchbox"), "runner");
    await waitFor(() => {
      expect(location()).toContain("q=runner");
    });
    await waitFor(() => {
      expect(
        get.mock.calls.some(
          ([url, config]) =>
            url === "/audit" &&
            (config?.params as Record<string, unknown> | undefined)?.q ===
              "runner",
        ),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(screen.queryByText("Аккаунт одобрен")).toBeNull();
    });
    expect(rows().length).toBeGreaterThan(0);
  });

  it("раздел из адреса: только его события", async () => {
    mount("/admin/audit?category=auth");
    await waitFor(() => {
      expect(rows().length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Аккаунт одобрен")).toBeNull();
    expect(screen.getAllByText("Вход").length).toBeGreaterThan(0);
    expect(screen.getByTestId("audit-filter-category")).toHaveTextContent(
      "Входы и аккаунты",
    );
  });

  it("«все действия этого человека» ставит фильтр «Кто»", async () => {
    const user = userEvent.setup();
    mount();
    const row = await rowOf("Аккаунт одобрен");
    await user.click(toggleOf(row));
    await user.click(
      within(row).getByRole("button", { name: "Все действия этого человека" }),
    );
    await waitFor(() => {
      expect(location()).toMatch(/actor_id=u_/);
    });
    const active = await screen.findByRole("group", {
      name: "Выбранные условия",
    });
    await waitFor(() => {
      expect(active).toHaveTextContent("Иван Сидоров");
    });
    await waitFor(() => {
      expect(screen.queryByText("Неудачная попытка входа")).toBeNull();
    });
    for (const r of rows()) expect(r).toHaveTextContent("Иван Сидоров");
  });

  it("журнал дописывается по курсору", async () => {
    const user = userEvent.setup();
    mount("/admin/audit?size=25");
    await screen.findByText("Сегодня");
    expect(rows()).toHaveLength(25);
    await user.click(screen.getByRole("button", { name: "Показать ещё" }));
    await waitFor(() => {
      expect(rows().length).toBeGreaterThan(25);
    });
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
    const empty = await screen.findByTestId("audit-empty", {}, SLOW);
    expect(empty).toHaveTextContent("Ничего не найдено");
    await user.click(
      within(empty).getByRole("button", { name: "Сбросить фильтры" }),
    );
    expect(await screen.findByText("Сегодня", {}, SLOW)).toBeVisible();
    expect(location()).toBe("");
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

describe("журнал большой установки", () => {
  beforeAll(async () => {
    installServerDemo();
    await ensureAdminUsersLocales();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("admin_scale");
  });
  afterEach(cleanup);

  // Большой мир собирается при первом запросе: тесту нужно больше времени.
  it(
    "администратор по имени, хотя его нет на первой странице людей",
    {
      timeout: 20_000,
    },
    async () => {
      mount();
      const row = await rowOf("Аккаунт одобрен");
      expect(row).toHaveTextContent("Иван Сидоров");
      expect(row).not.toHaveTextContent("Удалённый пользователь");
      // Оценка числа записей без фильтров: «из N» с разделителем разрядов.
      expect(screen.getByText(/Показано 50 из 250\s016/)).toBeVisible();
    },
  );
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

  it("цель: подпись сервера, иначе понятная цель, но не id", () => {
    const at = "2026-10-30T10:00:00Z";
    expect(
      auditTarget(
        event({ at, target: "u_1abcdef", target_label: "Анна Петрова" }),
      ),
    ).toEqual({ text: "Анна Петрова", key: null });
    // Подпись из details не повторяется в краткой строке: её ключ известен.
    expect(
      auditTarget(
        event({
          at,
          target: "org_01hxp3",
          target_label: "x",
          details: { slug: "x" },
        }),
      ),
    ).toEqual({ text: "x", key: "slug" });
    expect(auditTarget(event({ at, target: "rn_01hxb4" }))).toBeNull();
    expect(auditTarget(event({ at, target: "studio.example.org" }))).toEqual({
      text: "studio.example.org",
      key: null,
    });
  });

  it("псевдоним удалённого человека не выдаётся за имя", () => {
    expect(
      isPseudonym({ id: "deleted:3f9a", name: "deleted:3f9a", email: null }),
    ).toBe(true);
    expect(
      isPseudonym({ id: "u_1", name: "Анна", email: "a@example.org" }),
    ).toBe(false);
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
