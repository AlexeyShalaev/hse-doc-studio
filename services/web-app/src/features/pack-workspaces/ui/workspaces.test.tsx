import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { gitRemoteApi } from "@entities/git-remote";
import {
  PackWorkspaceSchema,
  packStudioApi,
  type PackWorkspace,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { CreateWorkspaceDialog } from "./CreateWorkspaceDialog";
import { WorkspaceList } from "./WorkspaceList";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures/PackWorkspace",
);
const fixture = (name: string): PackWorkspace =>
  PackWorkspaceSchema.parse(
    JSON.parse(readFileSync(join(FIXTURES, `${name}.json`), "utf8")),
  );

const wrap = (node: React.ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("рабочие пространства", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("пустой список зовёт создать пространство", async () => {
    vi.spyOn(packStudioApi, "workspaces").mockResolvedValue([]);
    const onCreate = vi.fn();
    wrap(<WorkspaceList onOpen={vi.fn()} onCreate={onCreate} />);
    await userEvent.click(await screen.findByTestId("ws-create-empty"));
    expect(onCreate).toHaveBeenCalled();
  });

  it("состояния карточек: клонируется, не удалось с причиной и повтором, готово", async () => {
    const cloning = fixture("git_cloning");
    const failed = { ...fixture("git_failed"), id: "f1" };
    const folder = fixture("folder");
    vi.spyOn(packStudioApi, "workspaces").mockResolvedValue([
      cloning,
      failed,
      folder,
    ]);
    const refresh = vi
      .spyOn(packStudioApi, "refreshWorkspace")
      .mockResolvedValue({
        ...failed,
        state: "cloning",
        busy: true,
        error: null,
      });
    const onOpen = vi.fn();
    wrap(<WorkspaceList onOpen={onOpen} onCreate={vi.fn()} />);

    const cloningCard = await screen.findByTestId(`ws-card-${cloning.id}`);
    expect(
      within(cloningCard).getByTestId("ws-state-cloning"),
    ).toBeInTheDocument();
    expect(within(cloningCard).getByTestId("ws-open")).toBeDisabled();

    const failedCard = screen.getByTestId("ws-card-f1");
    // Код git-синхронизации переводится словарём ошибок, а не текстом сервера.
    expect(within(failedCard).getByTestId("ws-error")).toHaveTextContent(
      i18n.t("errors:code.auth_failed"),
    );
    await userEvent.click(within(failedCard).getByTestId("ws-retry"));
    expect(refresh).toHaveBeenCalledWith("f1");

    const folderCard = screen.getByTestId(`ws-card-${folder.id}`);
    expect(folderCard).toHaveTextContent("/Users/anna/hse-doc-studio");
    await userEvent.click(
      within(folderCard).getByRole("button", { name: "Открыть" }),
    );
    expect(onOpen).toHaveBeenCalledWith(folder.id);
  });

  it("новое пространство над git: адрес, доступ по хосту, ветка", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    const created = fixture("git_cloning");
    const create = vi
      .spyOn(packStudioApi, "createWorkspace")
      .mockResolvedValue(created);
    const onCreated = vi.fn();
    wrap(
      <CreateWorkspaceDialog
        isOpen
        onClose={vi.fn()}
        onCreated={onCreated}
        allowFolder={false}
      />,
    );
    const submit = screen.getByTestId("ws-create-submit");
    expect(submit).toBeDisabled();
    await userEvent.type(
      screen.getByTestId("ws-create-url"),
      "https://github.com/AlexeyShalaev/hse-doc-studio",
    );
    await userEvent.type(screen.getByLabelText("Базовая ветка"), "master");
    await userEvent.click(submit);
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith({
        kind: "git",
        url: "https://github.com/AlexeyShalaev/hse-doc-studio",
        credential_id: null,
        base_branch: "master",
        packs_path: "packs",
        label: null,
        insecure_http: false,
      });
    });
    expect(onCreated).toHaveBeenCalledWith(created);
  });

  it("папка на диске только локально; отказ сервера показан словами", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    const { ApiError } = await import("@shared/api");
    vi.spyOn(packStudioApi, "createWorkspace").mockRejectedValue(
      new ApiError("x", "not_a_pack_repo", 400),
    );
    wrap(
      <CreateWorkspaceDialog
        isOpen
        onClose={vi.fn()}
        onCreated={vi.fn()}
        allowFolder
      />,
    );
    await userEvent.type(screen.getByTestId("ws-create-folder"), "/tmp/notes");
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "В папке нет паков",
    );
  });

  it("служебный доступ на сервере: без токена человека, флаг service_access", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    const created = fixture("git_service_access");
    const create = vi
      .spyOn(packStudioApi, "createWorkspace")
      .mockResolvedValue(created);
    wrap(
      <CreateWorkspaceDialog
        isOpen
        onClose={vi.fn()}
        onCreated={vi.fn()}
        allowFolder={false}
      />,
    );
    await userEvent.type(
      screen.getByTestId("ws-create-url"),
      "https://gitlab.hse.ru/fcs/packs.git",
    );
    // Памятка о токене под профиль прав «packs» для личного доступа.
    expect(
      screen.getByText("Какой токен нужен для веток и запросов на слияние"),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Служебный доступ" }),
    );
    expect(screen.getByTestId("ws-create-service-hint")).toBeInTheDocument();
    expect(screen.queryByLabelText("Доступ")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "git",
          url: "https://gitlab.hse.ru/fcs/packs.git",
          credential_id: null,
          service_access: true,
        }),
      );
    });
  });

  it("в локальной Студии служебного доступа нет", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    wrap(
      <CreateWorkspaceDialog
        isOpen
        onClose={vi.fn()}
        onCreated={vi.fn()}
        allowFolder
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Репозиторий git" }),
    );
    expect(
      screen.queryByRole("button", { name: "Служебный доступ" }),
    ).not.toBeInTheDocument();
  });
});
