import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("@widgets/ChatDock", () => ({ ChatDock: () => null }));
vi.mock("./RecentActivity", () => ({ RecentActivity: () => null }));

const caps = vi.hoisted(() => ({ lacking: new Set<string>() }));
vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useCapabilities: () => ({
    has: (name: string) => !caps.lacking.has(name),
    lacks: (name: string) => caps.lacking.has(name),
  }),
  useBootstrap: () => ({ data: { user: null } }),
}));

const projects = vi.hoisted(() => ({
  data: [] as Record<string, unknown>[],
  isLoading: false,
}));
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProjects: () => projects,
  useUpdateProject: () => ({ mutate: vi.fn() }),
  useTemplateMeta: () => ({ icon: () => null, accentHue: 200 }),
}));

import { WelcomePage } from "./WelcomePage";

const ANNA = "11111111-1111-4111-8111-111111111111";
const BORIS = "22222222-2222-4222-8222-222222222222";
const SERVER = "https://studio.example.org";

const localProject = (id: string, name: string) => ({
  id,
  name,
  folder: `/data/projects/${name}`,
  archived: false,
  pinned: false,
  supervisor: null,
  updated_at: "2026-11-01T09:00:00Z",
});

const cloudProject = (id: string, name: string, isLocal = false) => ({
  id,
  name,
  owner_name: "Анна Петрова",
  role: "owner",
  can_push: true,
  updated_at: "2026-11-02T09:00:00Z",
  is_local: isLocal,
});

const cloudServer = (over: Record<string, unknown> = {}) => ({
  credential_id: "cred-1",
  server_url: SERVER,
  host: "studio.example.org",
  state: "ok",
  total: 2,
  projects: [cloudProject(ANNA, "ВКР"), cloudProject(BORIS, "Курсовая")],
  ...over,
});

const Where = () => {
  const location = useLocation();
  return (
    <div data-testid="where">{`${location.pathname}${location.search}`}</div>
  );
};

const mount = (reply: object | Error) => {
  const get = vi.spyOn(apiClient, "get").mockImplementation((url: string) => {
    if (url === "/git/cloud/projects")
      return reply instanceof Error
        ? Promise.reject(reply)
        : Promise.resolve({ data: reply });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { get };
};

describe("главная локальной Студии: проекты облака", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    caps.lacking = new Set(["fs_browse_never"]);
    projects.data = [];
    projects.isLoading = false;
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("показывает облачные проекты рядом с локальными с пометкой «Облако», без слова git", async () => {
    projects.data = [localProject("p-local", "Локальный")];
    mount({ servers: [cloudServer()] });
    const cards = await screen.findAllByTestId("cloud-project-card");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByTestId("cloud-badge")).toHaveTextContent(
      "Облако",
    );
    expect(cards[0]).toHaveTextContent("Не открыт на этом компьютере");
    expect(screen.getByText("Локальный")).toBeVisible();
    expect(screen.queryByTestId("cloud-notices")?.textContent ?? "").toBe("");
  });

  it("не дублирует проект, открытый на компьютере: на его карточке пометка «Облако»", async () => {
    projects.data = [localProject(ANNA, "ВКР")];
    mount({
      servers: [
        cloudServer({
          projects: [
            cloudProject(ANNA, "ВКР", true),
            cloudProject(BORIS, "Курсовая"),
          ],
        }),
      ],
    });
    const cards = await screen.findAllByTestId("cloud-project-card");
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveTextContent("Курсовая");
    const local = document.querySelector(`[data-project-card="${ANNA}"]`);
    expect(local).not.toBeNull();
    expect(
      within(local as HTMLElement).getByTestId("cloud-badge"),
    ).toBeVisible();
    expect(screen.getAllByText("ВКР")).toHaveLength(1);
  });

  it("поиск и вкладка «Архив» действуют на облачные проекты", async () => {
    const user = userEvent.setup();
    mount({ servers: [cloudServer()] });
    await screen.findAllByTestId("cloud-project-card");
    await user.type(screen.getByRole("textbox"), "курсов");
    expect(screen.getAllByTestId("cloud-project-card")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Архив" }));
    expect(screen.queryByTestId("cloud-project-card")).toBeNull();
  });

  it("нажатие на облачную карточку открывает проект одним шагом: запрос открытия и окно прогресса", async () => {
    const user = userEvent.setup();
    mount({ servers: [cloudServer()] });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: { project_id: BORIS, operation_id: null },
    });
    const cards = await screen.findAllByTestId("cloud-project-card");
    await user.click(within(cards[1]!).getByTestId("cloud-open"));
    expect(post).toHaveBeenCalledWith(
      `/git/servers/cred-1/projects/${BORIS}/open`,
      undefined,
      expect.anything(),
    );
    expect(await screen.findByTestId("where")).toHaveTextContent(
      `/projects/${BORIS}`,
    );
  });

  it.each([
    ["expired", "Доступ к studio.example.org истёк"],
    ["revoked", "отозвал доступ"],
  ])(
    "сервер в состоянии %s: понятная строка и вход заново, локальные проекты на месте",
    async (state, text) => {
      const user = userEvent.setup();
      projects.data = [localProject("p-local", "Локальный")];
      mount({ servers: [cloudServer({ state, projects: [], total: 0 })] });
      expect(await screen.findByTestId("cloud-notices")).toHaveTextContent(
        text,
      );
      expect(screen.getByText("Локальный")).toBeVisible();
      expect(screen.queryByTestId("cloud-project-card")).toBeNull();
      await user.click(screen.getByTestId("cloud-reconnect"));
      expect(await screen.findByTestId("where")).toHaveTextContent(
        `/connect?server=${encodeURIComponent(SERVER)}`,
      );
    },
  );

  it("сервер недоступен: сообщение и повтор", async () => {
    mount({
      servers: [cloudServer({ state: "unreachable", projects: [], total: 0 })],
    });
    expect(await screen.findByTestId("cloud-notices")).toHaveTextContent(
      "сейчас недоступен",
    );
    expect(screen.getByTestId("cloud-retry")).toBeVisible();
  });

  it("не отвечает сама Студия: список локальных проектов остаётся, есть повтор", async () => {
    projects.data = [localProject("p-local", "Локальный")];
    const { get } = mount(new Error("network"));
    expect(await screen.findByTestId("cloud-notices")).toHaveTextContent(
      "Не удалось получить проекты облака",
    );
    expect(screen.getByText("Локальный")).toBeVisible();
    expect(get).toHaveBeenCalledWith("/git/cloud/projects", expect.anything());
  });

  it("пустое облако: короткая пометка, а не пустое состояние с мастером", async () => {
    projects.data = [localProject("p-local", "Локальный")];
    mount({ servers: [cloudServer({ projects: [], total: 0 })] });
    expect(await screen.findByTestId("cloud-notices")).toHaveTextContent(
      "пока нет проектов",
    );
    expect(screen.queryByTestId("cloud-project-card")).toBeNull();
  });

  it("список обрезан: сказано, сколько показано", async () => {
    mount({ servers: [cloudServer({ total: 700 })] });
    expect(await screen.findByTestId("cloud-notices")).toHaveTextContent(
      "первые 2 из 700",
    );
  });

  it("облачные проекты на странице сервера и без входа на сервер не запрашиваются", async () => {
    caps.lacking = new Set(["git_server_login"]);
    const { get } = mount({ servers: [cloudServer()] });
    await screen.findByText("Нет проектов", { exact: false }).catch(() => null);
    expect(get).not.toHaveBeenCalled();
    expect(screen.queryByTestId("cloud-project-card")).toBeNull();
  });
});
