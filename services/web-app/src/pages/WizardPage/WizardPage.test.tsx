import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";

vi.mock("@widgets/AppTitlebar", () => ({
  AppTitlebar: ({ projectName }: { projectName?: string }) => (
    <div data-testid="titlebar">{projectName}</div>
  ),
}));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("@widgets/ChatDock", () => ({ ChatDock: () => null }));
vi.mock("@features/project-create", () => ({
  ProjectCreateWizard: () => <div>create wizard</div>,
}));
vi.mock("@features/project-connect", () => ({
  ProjectConnectWizard: () => <div>connect wizard</div>,
}));
vi.mock("@features/folder-picker", () => ({
  FolderPickerModal: () => null,
  useInspectFolder: () => ({ data: undefined, isError: false }),
}));
// Возможности клиента: по умолчанию локальные (всё есть), сервер убирает папки.
const absent = new Set<string>();
vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useCapabilities: () => ({ lacks: (name: string) => absent.has(name) }),
}));
vi.mock("@features/git-remote", () => ({
  CloneWizard: ({
    folderless,
    initialTarget,
    onExit,
    onOpenProject,
  }: {
    folderless?: boolean;
    initialTarget?: { url: string; credentialId: string | null } | null;
    onExit: () => void;
    onOpenProject: (id: string) => void;
  }) => (
    <div>
      <div data-testid="folderless">{String(folderless ?? false)}</div>
      <div data-testid="target">{JSON.stringify(initialTarget)}</div>
      <button type="button" onClick={onExit}>
        exit
      </button>
      <button
        type="button"
        onClick={() => {
          onOpenProject("p-42");
        }}
      >
        open
      </button>
    </div>
  ),
}));

import { WizardPage } from "./WizardPage";

const Where = () => {
  const location = useLocation();
  return (
    <div data-testid="where">{`${location.pathname}${location.search}`}</div>
  );
};

const mount = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/wizard" element={<WizardPage />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );

describe("страница мастеров: режим клонирования", () => {
  afterEach(() => {
    cleanup();
  });

  it("режим clone показывает мастер клонирования и своё название", async () => {
    await i18n.changeLanguage("ru");
    mount("/wizard?mode=clone");
    expect(screen.getByTestId("titlebar")).toHaveTextContent(
      "Клонирование проекта",
    );
    expect(screen.getByTestId("target")).toHaveTextContent("null");
    expect(screen.queryByText("create wizard")).toBeNull();
    expect(screen.queryByText("connect wizard")).toBeNull();
  });

  it("передаёт мастеру адрес и доступ из строки запроса", () => {
    mount(
      "/wizard?mode=clone&url=https%3A%2F%2Fgithub.com%2Fhse-team%2Fpaper.git&credential=cred-1",
    );
    expect(JSON.parse(screen.getByTestId("target").textContent)).toEqual({
      url: "https://github.com/hse-team/paper.git",
      credentialId: "cred-1",
    });
  });

  it("выход возвращает на главную, «Открыть проект» ведёт в проект", async () => {
    const user = userEvent.setup();
    mount("/wizard?mode=clone");
    await user.click(screen.getByRole("button", { name: "open" }));
    expect(await screen.findByTestId("where")).toHaveTextContent(
      "/projects/p-42/documents",
    );
    cleanup();
    mount("/wizard?mode=clone");
    await user.click(screen.getByRole("button", { name: "exit" }));
    expect((await screen.findByTestId("where")).textContent).toBe("/");
  });

  it("другие режимы не затронуты", () => {
    mount("/wizard?mode=create");
    expect(screen.getByText("create wizard")).toBeInTheDocument();
    cleanup();
    mount("/wizard?mode=connect");
    expect(screen.getByText("connect wizard")).toBeInTheDocument();
    expect(screen.queryByTestId("target")).toBeNull();
  });
});

describe("страница мастеров: серверный режим без папок", () => {
  afterEach(() => {
    cleanup();
    absent.clear();
  });

  const useServer = () => {
    absent.add("fs_browse");
    absent.add("connect_folder");
  };

  it("локально клонирование идёт с выбором папки", () => {
    mount("/wizard?mode=clone");
    expect(screen.getByTestId("folderless")).toHaveTextContent("false");
  });

  it("на сервере клонирования по git нет: ссылка возвращает на главную", async () => {
    useServer();
    mount("/wizard?mode=clone");
    expect(screen.queryByTestId("folderless")).toBeNull();
    expect((await screen.findByTestId("where")).textContent).toBe("/");
  });

  it("на сервере подключения папки нет: ссылка возвращает на главную", async () => {
    useServer();
    mount("/wizard?mode=connect");
    expect(screen.queryByText("connect wizard")).toBeNull();
    expect((await screen.findByTestId("where")).textContent).toBe("/");
  });

  it("на сервере создание проекта доступно", () => {
    useServer();
    mount("/wizard?mode=create");
    expect(screen.getByText("create wizard")).toBeInTheDocument();
  });
});
