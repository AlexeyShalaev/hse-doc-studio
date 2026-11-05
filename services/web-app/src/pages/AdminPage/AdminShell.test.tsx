import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router";
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
import { i18n, loadAdminNamespaces } from "@shared/lib";
import { installViewport } from "@shared/lib/viewport/testing";
import userEvent from "@testing-library/user-event";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { AdminLayout } from "./AdminLayout";
import { AdminOverview } from "./AdminSections";

// Оболочка и сводка админки поверх демо-транспорта: те же запросы, что уйдут
// настоящему бэкенду.

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));

const mount = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter initialEntries={["/admin"]}>
          <Routes>
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<AdminOverview />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

describe("оболочка и сводка админки", () => {
  beforeAll(async () => {
    installServerDemo();
    await loadAdminNamespaces(["shell", "audit"]);
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("навигация по группам, счётчики, возврат в Студию и версия", async () => {
    activateServerScenario("ops_services_degraded");
    mount();
    const nav = screen.getByTestId("admin-nav");
    for (const group of ["Люди", "Сборки", "Система", "Настройки", "Журнал"]) {
      expect(within(nav).getByText(group)).toBeInTheDocument();
    }
    expect(screen.getByTestId("admin-nav-settings")).toHaveTextContent(
      "Вход и регистрация",
    );
    expect(
      await screen.findByTestId("admin-nav-count-users"),
    ).toHaveTextContent("3");
    // Три сервиса не работают, у раннеров перебои: как на странице «Сервисы».
    expect(
      await screen.findByTestId("admin-nav-count-services"),
    ).toHaveTextContent("4");
    // Места мало: у «Хранилища» точка без числа.
    expect(
      await screen.findByTestId("admin-nav-count-storage"),
    ).toHaveAttribute("data-tone", "danger");
    expect(screen.getByTestId("admin-back-to-studio")).toHaveAttribute(
      "href",
      "/",
    );
    expect(await screen.findByTestId("admin-version")).toHaveTextContent(
      "Версия 0.2.0",
    );
    expect(await screen.findByTestId("admin-instance-name")).toHaveTextContent(
      "HSE Doc Studio",
    );
  });

  it("сводка: числа, что требует внимания и последние действия людьми", async () => {
    activateServerScenario("admin_ready");
    mount();
    const people = await screen.findByTestId("overview-kpi-people");
    expect(await within(people).findByText("17")).toBeInTheDocument();
    expect(within(people).getByText("3 ждут одобрения")).toBeInTheDocument();
    // Занято столько же, сколько на странице «Хранилище»: диск проектов, а не только сборки.
    const storage = screen.getByTestId("overview-kpi-storage");
    expect(await within(storage).findByText("114 ГБ")).toBeInTheDocument();
    expect(
      await screen.findByTestId("overview-attention-approvals"),
    ).toHaveAttribute("href", "/admin/users?tab=approvals");
    const activity = screen.getByTestId("overview-activity");
    expect(
      await within(activity).findByText("Приглашение создано"),
    ).toBeInTheDocument();
    // Люди по имени, сырые идентификаторы на экран не попадают.
    expect(
      within(activity).getAllByText("Иван Сидоров").length,
    ).toBeGreaterThan(0);
    expect(within(activity).queryByText(/u_01hx/)).toBeNull();
    expect(screen.getByTestId("overview-quick-token")).toHaveAttribute(
      "href",
      "/admin/runners?create=token",
    );
  });

  it("упавший запрос показывает ошибку в своём блоке, остальное работает", async () => {
    activateServerScenario("admin_ready");
    const get = adminClient.get.bind(adminClient);
    vi.spyOn(adminClient, "get").mockImplementation((url, config) =>
      url === "/storage" || url === "/audit"
        ? Promise.reject(new Error("boom"))
        : get(url, config),
    );
    mount();
    const storage = await screen.findByTestId("overview-kpi-storage");
    expect(
      await within(storage).findByText("Не удалось загрузить"),
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId("overview-activity-failed"),
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId("overview-attention-failed"),
    ).toBeInTheDocument();
    const people = screen.getByTestId("overview-kpi-people");
    expect(await within(people).findByText("17")).toBeInTheDocument();
  });

  const diagBody = (accepted: boolean): Record<string, unknown> => {
    const at = "2026-11-05T10:00:00Z";
    const acceptance = {
      reason: "Бэкапы у хостера",
      by_name: "Анна",
      at,
      until: null,
    };
    return {
      overall: accepted ? "ok" : "warn",
      enabled: true,
      interval_s: 300,
      last_tick_at: at,
      checks: [
        {
          id: "backups",
          group: "operations",
          status: "warn",
          reason: "backups_disabled",
          hint: "backups_disabled",
          values: {},
          applicable: true,
          acceptable: !accepted,
          accepted: accepted ? acceptance : null,
          checked_at: at,
          status_since: at,
          duration_ms: 1,
        },
      ],
      accepted: accepted
        ? [{ check: "backups", acceptance, active: true }]
        : [],
      thresholds: [],
      notify: true,
    };
  };

  const withDiagnostics = (accepted: boolean) => {
    const get = adminClient.get.bind(adminClient);
    return vi
      .spyOn(adminClient, "get")
      .mockImplementation((url, config) =>
        url === "/diagnostics"
          ? Promise.resolve({ data: diagBody(accepted) })
          : get(url, config),
      );
  };

  it("самодиагностика: открытое предупреждение даёт точку у раздела", async () => {
    activateServerScenario("admin_ready");
    withDiagnostics(false);
    mount();
    const count = await screen.findByTestId("admin-nav-count-diagnostics");
    expect(count).toHaveTextContent("1");
    expect(count).toHaveAttribute("data-tone", "warning");
  });

  it("самодиагностика: принятое осознанно предупреждение точки не даёт", async () => {
    activateServerScenario("admin_ready");
    const get = withDiagnostics(true);
    mount();
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith("/diagnostics", expect.anything());
    });
    await screen.findByTestId("admin-nav-count-users");
    expect(screen.queryByTestId("admin-nav-count-diagnostics")).toBeNull();
  });

  it("сводка на английском", async () => {
    activateServerScenario("admin_ready");
    await i18n.changeLanguage("en");
    mount();
    expect(
      await screen.findByText("Installation overview"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("3 people are waiting for account approval"),
    ).toBeInTheDocument();
  });
});

describe("оболочка админки на телефоне", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  beforeAll(async () => {
    installServerDemo();
    await loadAdminNamespaces(["shell", "audit"]);
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    viewport?.restore();
    viewport = undefined;
  });

  it("вместо рейки кнопка с названием раздела, список разделов в шторке", async () => {
    activateServerScenario("ops_services_degraded");
    viewport = installViewport(390);
    const user = userEvent.setup();
    mount();
    expect(document.querySelector("nav.adm-nav")).toBeNull();
    const trigger = screen.getByTestId("admin-menu-trigger");
    expect(trigger).toHaveTextContent("Обзор");
    expect(screen.queryByTestId("admin-menu")).not.toBeInTheDocument();
    await user.click(trigger);
    const menu = screen.getByTestId("admin-menu");
    expect(menu.closest("[data-form]")).toHaveAttribute("data-form", "sheet");
    for (const group of ["Люди", "Сборки", "Система", "Настройки", "Журнал"]) {
      expect(within(menu).getByText(group)).toBeInTheDocument();
    }
    // Все разделы и возврат в Студию.
    expect(within(menu).getAllByRole("link")).toHaveLength(18);
    expect(
      await screen.findByTestId("admin-nav-count-services"),
    ).toHaveTextContent("4");
    expect(screen.getByTestId("admin-back-to-studio")).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("выбор раздела закрывает шторку", async () => {
    viewport = installViewport(360);
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByTestId("admin-menu-trigger"));
    await user.click(screen.getByTestId("admin-nav-runners"));
    expect(screen.queryByTestId("admin-menu")).not.toBeInTheDocument();
  });

  it("на десктопе рейка на месте", () => {
    viewport = installViewport(1360);
    mount();
    expect(screen.getByTestId("admin-nav")).toBeInTheDocument();
    expect(screen.queryByTestId("admin-menu-trigger")).toBeNull();
  });
});
