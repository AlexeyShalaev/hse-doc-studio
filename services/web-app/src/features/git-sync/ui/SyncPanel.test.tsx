import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  gitSyncApi,
  useSyncUiStore,
  type SyncStatusView,
} from "@entities/git-sync";
import {
  connected,
  noRemote,
  runningOperation,
} from "../testing/statusFactory";
import {
  PROJECT_ID,
  renderSync,
  resetSyncEnvironment,
} from "../testing/renderSync";

const project = { access: { mode: "full", reasons: [] } };
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: project }),
}));

import { SyncPanel } from "./SyncPanel";

const mount = (
  status: SyncStatusView,
  props: Partial<Parameters<typeof SyncPanel>[0]> = {},
) => {
  vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(status);
  const onConnect = vi.fn();
  const onShowInHistory = vi.fn();
  const view = renderSync(
    <SyncPanel
      projectId={PROJECT_ID}
      onConnect={onConnect}
      onShowInHistory={onShowInHistory}
      {...props}
    />,
  );
  return { ...view, onConnect, onShowInHistory };
};

describe("SyncPanel", () => {
  beforeEach(async () => {
    await resetSyncEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders nothing when the backend cannot sync", async () => {
    const { container } = mount({ ...noRemote(), supported: false });
    await waitFor(() => {
      expect(gitSyncApi.getStatus).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("sync-panel")).toBeNull();
    expect(screen.queryByTestId("sync-panel-empty")).toBeNull();
    expect(container.querySelector(".card")).toBeNull();
  });

  it("hands connect to the page and bundle to the optional callback", async () => {
    const user = userEvent.setup();
    const onBundle = vi.fn();
    const { onConnect } = mount(noRemote(), { onBundle });
    await user.click(
      await screen.findByRole("button", { name: "Подключить репозиторий" }),
    );
    await user.click(screen.getByRole("button", { name: "Обмен файлом" }));
    expect(onConnect).toHaveBeenCalledTimes(1);
    expect(onBundle).toHaveBeenCalledTimes(1);
  });

  it("runs and checks through the shared command queue", async () => {
    const user = userEvent.setup();
    mount(connected());
    await user.click(
      await screen.findByRole("button", { name: /Синхронизировать/ }),
    );
    expect(useSyncUiStore.getState().command?.kind).toBe("run");
    useSyncUiStore.setState({ command: null });
    await user.click(
      screen.getByRole("button", { name: "Проверить обновления" }),
    );
    expect(useSyncUiStore.getState().command?.kind).toBe("check");
  });

  it("opens the access dialog and navigates to settings and conflicts", async () => {
    const user = userEvent.setup();
    const view = mount(
      connected({
        ui_state: "auth_failed",
        health: "unauthenticated",
        last_error: {
          code: "auth_failed",
          detail: "x",
          at: "2026-10-26T10:00:00Z",
        },
      }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Обновить доступ" }),
    );
    expect(useSyncUiStore.getState().connectDialog).toEqual({
      mode: "fix_access",
    });
    await user.click(
      screen.getByRole("button", { name: "Настройки синхронизации" }),
    );
    expect(view.getByTestId("location")).toHaveTextContent(
      `/projects/${PROJECT_ID}/project-settings/sync`,
    );
  });

  it("goes to the conflict screen from the conflicts state", async () => {
    const user = userEvent.setup();
    const view = mount(
      connected({
        ui_state: "conflicts",
        pending: { session_id: "s", files_total: 2, files_open: 2 },
      }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Разобрать конфликты" }),
    );
    expect(view.getByTestId("location")).toHaveTextContent(
      `/projects/${PROJECT_ID}/sync/conflicts`,
    );
  });

  it("cancels the running operation by its id", async () => {
    const user = userEvent.setup();
    const cancel = vi.spyOn(gitSyncApi, "cancelOperation").mockResolvedValue({
      id: "op-1",
      kind: "sync",
      project_id: PROJECT_ID,
      status: "cancelled",
      phase: "fetch",
      percent: null,
      message: null,
      cancellable: false,
      started_at: "2026-10-26T10:00:00Z",
      finished_at: "2026-10-26T10:00:03Z",
      result: null,
      error: null,
    });
    mount(
      connected({
        ui_state: "syncing",
        operation: runningOperation({ id: "op-1" }),
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Отменить" }));
    await waitFor(() => {
      expect(cancel).toHaveBeenCalledWith("op-1");
    });
  });

  it("acknowledges the shared folder warning on the server", async () => {
    const user = userEvent.setup();
    const status = connected({
      shared_folder: { provider: "dropbox", root: "/d", acknowledged: false },
    });
    const update = vi
      .spyOn(gitSyncApi, "updateSettings")
      .mockResolvedValue(status);
    mount(status);
    await user.click(await screen.findByRole("button", { name: "Понятно" }));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(PROJECT_ID, {
        shared_folder_ack: true,
      });
    });
  });

  it("shows the details of the selected incoming commit from the render prop", async () => {
    const user = userEvent.setup();
    const render = vi.fn((id: string) => <div>Различия {id}</div>);
    mount(
      connected({
        ui_state: "behind",
        relation: "behind",
        behind: 1,
        incoming: [
          {
            id: "abc1234",
            short_id: "abc1234",
            message: "Новая глава",
            author: "Анна Петрова",
            author_email: "anna@edu.hse.ru",
            created_at: "2026-10-26T09:00:00Z",
            kind: "edit",
          },
        ],
      }),
      { renderIncomingDetails: render },
    );
    await user.click(
      await screen.findByRole("button", { name: /Новая глава/ }),
    );
    expect(await screen.findByText("Различия abc1234")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Новая глава/ }));
    expect(screen.queryByText("Различия abc1234")).toBeNull();
  });
});
