import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("@widgets/ChatDock", () => ({ ChatDock: () => null }));
vi.mock("./RecentActivity", () => ({ RecentActivity: () => null }));

const projects: {
  data: unknown[] | undefined;
  isLoading: boolean;
  isError: boolean;
} = { data: [], isLoading: false, isError: false };
const refetch = vi.fn();
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProjects: () => ({ ...projects, refetch, isFetching: false }),
  useUpdateProject: () => ({ mutate: vi.fn() }),
  useTemplateMeta: () => ({
    icon: () => null,
    accentHue: 200,
    label: "Шаблон",
  }),
}));

import { WelcomePage } from "./WelcomePage";

const SERVER: Bootstrap = {
  ...LOCAL_BOOTSTRAP,
  mode: "server",
  capabilities: {
    ...LOCAL_BOOTSTRAP.capabilities,
    fs_browse: false,
    connect_folder: false,
    open_in_editor: false,
    move_project: false,
    docker_ui: false,
    self_update: false,
    local_services_ui: false,
  },
  user: {
    id: "u1",
    name: "Анна Петрова",
    email: "anna@example.org",
    avatar_initials: "АП",
    is_instance_admin: false,
    email_verified: true,
    locale: "ru",
    org_roles: [{ slug: "msp", name: "МСПИН 2025", role: "member" }],
  },
  csrf_token: "tok",
};

const item = (id: string, name: string, extra: Record<string, unknown>) => ({
  id,
  name,
  folder: "",
  lock: { pack_id: "", template_id: "", version: "", engine: "xelatex" },
  kind: "project",
  staffing: "solo",
  lang: "ru",
  updated_at: "2026-10-26T18:20:00Z",
  pinned: false,
  archived: false,
  shared_enabled: true,
  ...extra,
});

const OWN = item("p1", "Свой проект", {
  owner: { kind: "user", id: "u1", name: "Анна Петрова", slug: null },
  my_role: "owner",
});
const ORG = item("p2", "Проект организации", {
  owner: { kind: "org", id: "o1", name: "МСПИН 2025", slug: "msp" },
  my_role: "reviewer",
});
const SHARED = item("p3", "Чужой проект", {
  owner: { kind: "user", id: "u2", name: "Павел Орлов", slug: null },
  my_role: "reader",
});

const Where = () => {
  const location = useLocation();
  return (
    <div data-testid="where">{`${location.pathname}${location.search}`}</div>
  );
};

const mount = (bootstrap: Bootstrap = SERVER) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("главная в серверном режиме", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    projects.data = [OWN, ORG, SHARED];
    projects.isLoading = false;
    projects.isError = false;
  });
  afterEach(() => {
    cleanup();
  });

  it("нет кнопки «Открыть папку», остаются клонирование и создание", () => {
    mount();
    expect(screen.queryByRole("button", { name: /Открыть папку/ })).toBeNull();
    expect(
      screen.getAllByRole("button", { name: "Клонировать из git" }),
    ).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Новый проект" })).toBeVisible();
    expect(screen.getByText("Сервер · Общее хранилище")).toBeVisible();
  });

  it("карточки показывают владельца и роль, а не папку", () => {
    mount();
    const cards = screen.getAllByTestId("project-owner");
    expect(cards.map((c) => c.textContent)).toEqual([
      "Организация: МСПИН 2025",
      "Личный проект",
      "Владелец: Павел Орлов",
    ]);
    // Роль владельца не подписывается, остальные подписаны.
    expect(
      screen.getAllByTestId("project-role").map((c) => c.textContent),
    ).toEqual(["Рецензент", "Читатель"]);
  });

  it("закрепить и архивировать может только владелец", () => {
    mount();
    // Три карточки, кнопки только у проекта с ролью owner.
    expect(screen.getAllByTestId("project-owner")).toHaveLength(3);
    expect(screen.getAllByTestId("project-pin")).toHaveLength(1);
    expect(screen.getAllByTestId("project-archive")).toHaveLength(1);
  });

  it("фильтр «Мои / Организации» делит проекты по владельцу", async () => {
    const user = userEvent.setup();
    mount();
    const group = screen.getByRole("group", { name: "Чьи проекты" });
    await user.click(
      within(group).getByRole("button", { name: "Организации" }),
    );
    expect(screen.getByText("Проект организации")).toBeVisible();
    expect(screen.queryByText("Свой проект")).toBeNull();
    await user.click(within(group).getByRole("button", { name: "Мои" }));
    expect(screen.queryByText("Проект организации")).toBeNull();
    expect(screen.getByText("Свой проект")).toBeVisible();
  });

  it("без организаций переключателя нет", () => {
    projects.data = [OWN];
    mount({ ...SERVER, user: { ...SERVER.user!, org_roles: [] } });
    expect(screen.queryByRole("group", { name: "Чьи проекты" })).toBeNull();
  });

  it("пустое состояние без «подключить папку» и с подсказкой про приглашение", () => {
    projects.data = [];
    mount();
    expect(screen.getByText("Проектов пока нет")).toBeVisible();
    expect(
      screen.getByText(/попросите владельца пригласить вас/),
    ).toBeVisible();
    expect(screen.queryByText(/подключите существующую папку/)).toBeNull();
  });

  it("пустой раздел предлагает вернуться ко всем", async () => {
    const user = userEvent.setup();
    projects.data = [OWN];
    mount();
    const group = screen.getByRole("group", { name: "Чьи проекты" });
    await user.click(
      within(group).getByRole("button", { name: "Организации" }),
    );
    expect(screen.getByText("В этом разделе проектов нет")).toBeVisible();
    const empty = screen.getByText("В этом разделе проектов нет").parentElement;
    if (!empty) throw new Error("no empty state");
    await user.click(within(empty).getByRole("button", { name: "Все" }));
    expect(screen.getByText("Свой проект")).toBeVisible();
  });

  it("сбой загрузки это отдельное состояние с повтором", async () => {
    const user = userEvent.setup();
    projects.data = undefined;
    projects.isError = true;
    mount();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Не удалось загрузить проекты",
    );
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("на английском те же состояния переведены", async () => {
    await i18n.changeLanguage("en");
    projects.data = [];
    mount();
    expect(screen.getByText("No projects yet")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Open folder/ })).toBeNull();
  });

  it("локальный режим: кнопка «Открыть папку» и папка на карточке", () => {
    projects.data = [item("p9", "Локальный", { folder: "/tmp/local" })];
    mount(LOCAL_BOOTSTRAP);
    expect(screen.getByRole("button", { name: /Открыть папку/ })).toBeVisible();
    expect(screen.getByText("/tmp/local")).toBeVisible();
    expect(screen.queryByTestId("project-owner")).toBeNull();
  });

  it("импорт из zip: кнопка в шапке и в пустом списке открывает окно, в локальном режиме её нет", async () => {
    const user = userEvent.setup();
    projects.data = [];
    mount();
    expect(
      screen.getByRole("button", { name: "Загрузить проект из zip" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Импорт из zip" }));
    expect(
      await screen.findByText("Импорт проекта из локальной Студии"),
    ).toBeVisible();
    cleanup();
    mount(LOCAL_BOOTSTRAP);
    expect(screen.queryByRole("button", { name: "Импорт из zip" })).toBeNull();
  });
});
