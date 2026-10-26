import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@features/git-sync", () => ({ SyncControl: () => null }));
vi.mock("@features/author-profile", () => ({
  ProfilePromptDialog: ({
    isOpen,
    onSaved,
  }: {
    isOpen: boolean;
    onSaved?: () => void;
  }) =>
    isOpen ? (
      <button type="button" onClick={onSaved}>
        Окно профиля
      </button>
    ) : null,
}));
vi.mock("@features/git-exchange", () => ({
  BundleExchangeDialog: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div>Окно обмена файлом</div> : null,
}));
vi.mock("@features/git-remote", () => ({
  ConnectRemoteDialog: ({
    onCloneInstead,
  }: {
    onCloneInstead?: (target: {
      url: string;
      credentialId: string | null;
    }) => void;
  }) => (
    <button
      type="button"
      onClick={() => {
        onCloneInstead?.({
          url: "https://github.com/hse-team/paper.git",
          credentialId: "cred-1",
        });
      }}
    >
      Клонировать в новую папку
    </button>
  ),
}));

import { useSyncUiStore } from "@entities/git-sync";
import { SyncCluster } from "./SyncCluster";

const Where = () => {
  const location = useLocation();
  return (
    <div data-testid="where">{`${location.pathname}${location.search}`}</div>
  );
};

describe("SyncCluster: проект репозитория другой, клонируем", () => {
  afterEach(() => {
    cleanup();
    useSyncUiStore.setState({
      profileDialogOpen: false,
      bundleDialogOpen: false,
    });
  });

  it("ведёт в мастер клонирования с готовым адресом и доступом", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route
            path="/projects/:id"
            element={<SyncCluster projectId="p1" />}
          />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>,
    );
    await user.click(
      screen.getByRole("button", { name: "Клонировать в новую папку" }),
    );
    const where = (await screen.findByTestId("where")).textContent;
    expect(where).toContain("/wizard?");
    const query = new URLSearchParams(where.split("?")[1]);
    expect(query.get("mode")).toBe("clone");
    expect(query.get("url")).toBe("https://github.com/hse-team/paper.git");
    expect(query.get("credential")).toBe("cred-1");
  });

  it("показывает окно «Представься» по просьбе из общего состояния и закрывает после сохранения", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <SyncCluster projectId="p1" />
      </MemoryRouter>,
    );
    expect(screen.queryByText("Окно профиля")).toBeNull();
    act(() => {
      useSyncUiStore.getState().openProfileDialog();
    });
    await user.click(await screen.findByText("Окно профиля"));
    expect(useSyncUiStore.getState().profileDialogOpen).toBe(false);
  });

  it("показывает окно обмена файлом по просьбе из общего состояния", () => {
    render(
      <MemoryRouter>
        <SyncCluster projectId="p1" />
      </MemoryRouter>,
    );
    expect(screen.queryByText("Окно обмена файлом")).toBeNull();
    act(() => {
      useSyncUiStore.getState().openBundleDialog();
    });
    expect(screen.getByText("Окно обмена файлом")).toBeInTheDocument();
  });
});
