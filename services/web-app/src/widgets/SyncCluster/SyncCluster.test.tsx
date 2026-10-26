import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@features/git-sync", () => ({ SyncControl: () => null }));
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
});
