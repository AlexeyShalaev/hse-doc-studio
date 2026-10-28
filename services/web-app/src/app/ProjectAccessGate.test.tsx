import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { useRecentProjectsStore } from "@shared/lib";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));

const query: { error: unknown } = { error: null };
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: undefined, error: query.error }),
}));

import { ProjectAccessGate } from "./ProjectAccessGate";

const SERVER: Bootstrap = {
  ...LOCAL_BOOTSTRAP,
  mode: "server",
  user: {
    id: "u1",
    name: "Анна Петрова",
    email: "anna@example.org",
    avatar_initials: "АП",
    is_instance_admin: false,
    email_verified: true,
    locale: "ru",
    org_roles: [],
  },
  csrf_token: "tok",
};

const Where = () => <span data-testid="where">{useLocation().pathname}</span>;

const mount = (bootstrap: Bootstrap) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/projects/p-dead/documents"]}>
        <Where />
        <Routes>
          <Route element={<ProjectAccessGate />}>
            <Route
              path="/projects/:projectId/documents"
              element={<div>workspace</div>}
            />
          </Route>
          <Route path="*" element={<div>home</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const notFound = () => new ApiError("Not found", "not_found", 404);

describe("охранник проекта", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    query.error = null;
    useRecentProjectsStore.setState({
      recent: [
        { id: "p-dead", at: 2 },
        { id: "p-live", at: 1 },
      ],
    });
  });
  afterEach(() => {
    cleanup();
  });

  it("доступный проект открывает рабочую область, недавние целы", () => {
    mount(SERVER);
    expect(screen.getByText("workspace")).toBeInTheDocument();
    expect(useRecentProjectsStore.getState().recent).toHaveLength(2);
  });

  it("404 показывает нейтральную страницу и чистит недавние", () => {
    query.error = notFound();
    mount(SERVER);
    expect(
      screen.getByRole("heading", {
        name: "Проект не найден или у вас нет доступа",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("workspace")).toBeNull();
    expect(useRecentProjectsStore.getState().recent).toEqual([
      { id: "p-live", at: 1 },
    ]);
  });

  it("кнопка ведёт к списку проектов", async () => {
    query.error = notFound();
    mount(SERVER);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "К моим проектам" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/");
    expect(screen.getByText("home")).toBeInTheDocument();
  });

  it("другая ошибка (сеть, 500) страницу доступа не показывает", () => {
    query.error = new ApiError("boom", "unknown_error", 500);
    mount(SERVER);
    expect(screen.getByText("workspace")).toBeInTheDocument();
    expect(useRecentProjectsStore.getState().recent).toHaveLength(2);
  });

  it("локальный режим без аккаунта работает как раньше", () => {
    query.error = notFound();
    mount(LOCAL_BOOTSTRAP);
    expect(screen.getByText("workspace")).toBeInTheDocument();
    expect(useRecentProjectsStore.getState().recent).toHaveLength(2);
  });
});
