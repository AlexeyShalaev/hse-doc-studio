import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
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
import { i18n } from "@shared/lib";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { loadAdminLocales } from "./adminLocales";
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
    await loadAdminLocales();
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
    expect(
      await screen.findByTestId("admin-nav-count-services"),
    ).toHaveTextContent("3");
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
    expect(await within(people).findByText("13")).toBeInTheDocument();
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
    expect(await within(people).findByText("13")).toBeInTheDocument();
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
