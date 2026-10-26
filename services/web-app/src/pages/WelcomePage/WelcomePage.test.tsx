import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("@widgets/ChatDock", () => ({ ChatDock: () => null }));
vi.mock("./RecentActivity", () => ({ RecentActivity: () => null }));

const projects: { data: unknown[]; isLoading: boolean } = {
  data: [],
  isLoading: false,
};
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProjects: () => projects,
  useUpdateProject: () => ({ mutate: vi.fn() }),
  useTemplateMeta: () => ({ icon: () => null, accentHue: 200 }),
}));

import { WelcomePage } from "./WelcomePage";

const Where = () => {
  const location = useLocation();
  return (
    <div data-testid="where">{`${location.pathname}${location.search}`}</div>
  );
};

const nth = (items: HTMLElement[], index: number): HTMLElement => {
  const item = items[index];
  if (!item) throw new Error(`no element at ${String(index)}`);
  return item;
};

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("главная: вход в клонирование", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    projects.data = [];
    projects.isLoading = false;
  });
  afterEach(() => {
    cleanup();
  });

  it("в заголовке есть кнопка «Клонировать из git» между «Открыть папку» и «Новый проект»", () => {
    mount();
    const buttons = screen
      .getAllByRole("button")
      .map((button) => button.textContent.trim());
    const open = buttons.indexOf("Открыть папку…");
    const clone = buttons.indexOf("Клонировать из git");
    const create = buttons.indexOf("Новый проект");
    expect(open).toBeGreaterThanOrEqual(0);
    expect(clone).toBe(open + 1);
    expect(create).toBe(clone + 1);
  });

  it("кнопка в заголовке открывает мастер клонирования", async () => {
    const user = userEvent.setup();
    mount();
    // В заголовке кнопка одна: во втором месте (пустое состояние) их две.
    await user.click(
      nth(screen.getAllByRole("button", { name: "Клонировать из git" }), 0),
    );
    expect(await screen.findByTestId("where")).toHaveTextContent(
      "/wizard?mode=clone",
    );
  });

  it("в пустом списке проектов то же действие есть и в пустом состоянии", async () => {
    const user = userEvent.setup();
    mount();
    const buttons = screen.getAllByRole("button", {
      name: "Клонировать из git",
    });
    expect(buttons).toHaveLength(2);
    await user.click(nth(buttons, 1));
    expect(await screen.findByTestId("where")).toHaveTextContent(
      "/wizard?mode=clone",
    );
  });

  it("когда проекты есть, пустого состояния с клонированием нет, остаётся кнопка в заголовке", () => {
    projects.data = [
      {
        id: "p1",
        name: "Курсовая",
        folder: "/tmp/p1",
        archived: false,
        pinned: false,
        supervisor: null,
      },
    ];
    mount();
    expect(
      screen.getAllByRole("button", { name: "Клонировать из git" }),
    ).toHaveLength(1);
  });
});
