import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";

const createProject = vi.fn((_payload: unknown) =>
  Promise.resolve({ id: "p-new" }),
);
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useCreateProject: () => ({ mutateAsync: createProject, isPending: false }),
  useProjectSuggestions: () => ({ data: undefined }),
}));
vi.mock("@entities/template-catalog", () => ({
  usePacks: () => ({ data: [], isLoading: false }),
  useVersions: () => ({ data: [], isLoading: false }),
  useVersionDetail: () => ({
    data: {
      supported_staffing: ["solo", "team"],
      meta_fields: {},
      meta_groups: [],
      documents: [],
      author_group_placeholder: "",
    },
  }),
}));
vi.mock("@entities/hse-person", () => ({ HsePersonLookupButton: () => null }));
vi.mock("@features/folder-picker", () => ({ FolderPickerModal: () => null }));

import { ProjectCreateWizard } from "./ProjectCreateWizard";
import { useCreateWizard } from "../model/useCreateWizard";

const SERVER: Bootstrap = {
  ...LOCAL_BOOTSTRAP,
  mode: "server",
  capabilities: {
    ...LOCAL_BOOTSTRAP.capabilities,
    fs_browse: false,
    connect_folder: false,
  },
  user: {
    id: "u1",
    name: "Иван Сидоров",
    email: "ivan@example.org",
    avatar_initials: "ИС",
    is_instance_admin: true,
    email_verified: true,
    locale: "ru",
    org_roles: [
      { slug: "msp", name: "МСПИН 2025", role: "owner" },
      { slug: "lab", name: "Лаборатория", role: "member" },
    ],
  },
  csrf_token: "tok",
};

const mount = (bootstrap: Bootstrap) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProjectCreateWizard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const filled = {
  packId: "hse-cs-sse",
  templateId: "course-project",
  version: "1.0.0",
  title: "Bertie",
  authors: [
    { name: "Иван", group: "", topic: "", slug: "ivan", managed: true },
  ],
};

describe("мастер создания проекта на сервере", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    createProject.mockClear();
    useCreateWizard.getState().reset();
  });
  afterEach(() => {
    cleanup();
  });

  it("вместо шага «Папка» идёт шаг «Название», без поля папки и выбора папки", () => {
    useCreateWizard.setState({ ...filled, step: 4, maxReached: 4 });
    mount(SERVER);
    const sidebar = screen.getAllByRole("button");
    expect(sidebar.some((b) => b.textContent.includes("Папка"))).toBe(false);
    expect(sidebar.some((b) => b.textContent.includes("Название"))).toBe(true);
    expect(screen.queryByText("Обзор…")).toBeNull();
    expect(screen.queryByText("Локальная папка")).toBeNull();
    expect(screen.getByPlaceholderText(/Diff-аналитика/)).toBeInTheDocument();
  });

  it("владельцем можно выбрать только организацию, где ты администратор", () => {
    useCreateWizard.setState({ ...filled, step: 4, maxReached: 4 });
    mount(SERVER);
    const group = screen.getByRole("radiogroup", { name: "Владелец проекта" });
    const options = within(group)
      .getAllByRole("radio")
      .map((r) => r.textContent);
    expect(options).toHaveLength(2);
    expect(options[0]).toContain("Я");
    expect(options[1]).toContain("МСПИН 2025");
    expect(group.textContent).not.toContain("Лаборатория");
  });

  it("студент без организаций выбора владельца не видит", () => {
    useCreateWizard.setState({ ...filled, step: 4, maxReached: 4 });
    mount({
      ...SERVER,
      user: { ...SERVER.user!, org_roles: [] },
    });
    expect(screen.queryByRole("radiogroup")).toBeNull();
  });

  it("выбор организации уходит в owner_org_slug, папки в запросе нет", async () => {
    const user = userEvent.setup();
    useCreateWizard.setState({ ...filled, step: 4, maxReached: 4 });
    mount(SERVER);
    await user.click(screen.getByRole("radio", { name: /МСПИН 2025/ }));
    useCreateWizard.setState({ step: 10, maxReached: 10 });
    await user.click(
      await screen.findByRole("button", { name: "Создать проект" }),
    );
    expect(createProject).toHaveBeenCalledTimes(1);
    const payload = createProject.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload).toMatchObject({ name: "Bertie", owner_org_slug: "msp" });
    expect("folder" in payload).toBe(false);
  });

  it("личный проект: owner_org_slug пустой", async () => {
    const user = userEvent.setup();
    useCreateWizard.setState({ ...filled, step: 10, maxReached: 10 });
    mount(SERVER);
    await user.click(
      await screen.findByRole("button", { name: "Создать проект" }),
    );
    const payload = createProject.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload.owner_org_slug).toBeNull();
  });

  it("локальный режим: шаг «Папка» и путь в запросе, как раньше", async () => {
    const user = userEvent.setup();
    useCreateWizard.setState({
      ...filled,
      folder: "/tmp/bertie",
      step: 10,
      maxReached: 10,
    });
    mount(LOCAL_BOOTSTRAP);
    expect(
      screen
        .getAllByRole("button")
        .some((b) => b.textContent.includes("Папка")),
    ).toBe(true);
    await user.click(
      await screen.findByRole("button", { name: "Создать проект" }),
    );
    const payload = createProject.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload.folder).toBe("/tmp/bertie");
    expect("owner_org_slug" in payload).toBe(false);
  });
});
