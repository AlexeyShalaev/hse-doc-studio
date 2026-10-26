import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  gitSyncApi,
  gitSyncKeys,
  useSyncUiStore,
  type GitOperation,
  type SyncResult,
} from "@entities/git-sync";
import { ApiError } from "@shared/api";
import { registerPendingSave, useToastStore } from "@shared/lib";
import { connected, runningOperation } from "../testing/statusFactory";
import {
  PROJECT_ID,
  makeClient,
  resetSyncEnvironment,
} from "../testing/renderSync";

const project = { access: { mode: "full", reasons: [] } };
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: project }),
}));

import { useSyncController } from "./useSyncController";

const RESULT: SyncResult = {
  outcome: "merged",
  pulled_commits: 2,
  pushed_commits: 3,
  merge_commit: "abc1234",
  files_changed: 4,
  auto: [],
  conflicts: null,
  warnings: [],
};

const operation = (overrides: Partial<GitOperation> = {}): GitOperation => ({
  id: "op-1",
  kind: "sync",
  project_id: PROJECT_ID,
  status: "succeeded",
  phase: "push",
  percent: 100,
  message: null,
  cancellable: false,
  started_at: "2026-10-26T10:00:00Z",
  finished_at: "2026-10-26T10:00:05Z",
  result: RESULT,
  error: null,
  ...overrides,
});

const toasts = () => useToastStore.getState().toasts;

const setup = (status = connected()) => {
  vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(status);
  vi.spyOn(gitSyncApi, "fetchRemote").mockResolvedValue(status);
  const client = makeClient();
  const Probe = ({ children }: { children: ReactNode }) => {
    const location = useLocation();
    return (
      <>
        <span data-testid="at">{location.pathname}</span>
        {children}
      </>
    );
  };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/documents`]}>
        <Probe>{children}</Probe>
      </MemoryRouter>
    </QueryClientProvider>
  );
  const hook = renderHook(
    () => ({ controller: useSyncController(PROJECT_ID), loc: useLocation() }),
    { wrapper },
  );
  return { client, ...hook };
};

describe("useSyncController", () => {
  beforeEach(async () => {
    await resetSyncEnvironment();
    useToastStore.getState().clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("flushes pending editor saves before it asks the server to start", async () => {
    const order: string[] = [];
    const unregister = registerPendingSave(async () => {
      await Promise.resolve();
      order.push("flush");
    });
    vi.spyOn(gitSyncApi, "startSync").mockImplementation(() => {
      order.push("start");
      return Promise.resolve({ operation_id: "op-1" });
    });
    vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
      operation({ status: "running", result: null }),
    );
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    await act(async () => {
      await result.current.controller.run();
    });
    expect(order).toEqual(["flush", "start"]);
    unregister();
  });

  it("does not start while an editor could not save, and says why", async () => {
    const unregister = registerPendingSave(() => {
      throw new Error("disk full");
    });
    const start = vi.spyOn(gitSyncApi, "startSync");
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    await act(async () => {
      await result.current.controller.run();
    });
    expect(start).not.toHaveBeenCalled();
    expect(toasts().map((t) => t.kind)).toEqual(["error"]);
    expect(toasts()[0]?.title).toBe("Правки не сохранены");
    unregister();
  });

  it("follows the operation from the first phase to the outcome and toasts once", async () => {
    vi.spyOn(gitSyncApi, "startSync").mockResolvedValue({
      operation_id: "op-1",
    });
    const poll = vi
      .spyOn(gitSyncApi, "getOperation")
      .mockResolvedValueOnce(
        operation({
          status: "running",
          phase: "fetch",
          percent: 30,
          result: null,
        }),
      )
      .mockResolvedValue(operation());
    const { result, client } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    await act(async () => {
      await result.current.controller.run();
    });
    await waitFor(() => {
      expect(result.current.controller.operation?.phase).toBe("fetch");
    });
    expect(toasts()).toHaveLength(0);

    await act(async () => {
      await client.refetchQueries({ queryKey: gitSyncKeys.operation("op-1") });
    });
    await waitFor(() => {
      expect(toasts()).toHaveLength(1);
    });
    expect(toasts()[0]).toMatchObject({
      kind: "success",
      title: "Синхронизировано",
      message: "Получено версий: 2, отправлено: 3",
    });

    // Повторные чтения операции и обновления кэша тост не дублируют.
    await act(async () => {
      await client.invalidateQueries({ queryKey: gitSyncKeys.all });
      await client.refetchQueries({ queryKey: gitSyncKeys.operation("op-1") });
    });
    expect(toasts()).toHaveLength(1);
    expect(poll).toHaveBeenCalled();
  });

  it("goes to the conflict screen when the user who started it gets conflicts", async () => {
    vi.spyOn(gitSyncApi, "startSync").mockResolvedValue({
      operation_id: "op-1",
    });
    vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
      operation({
        result: {
          ...RESULT,
          outcome: "conflicts",
          conflicts: { files_total: 3, files_open: 2 },
        },
      }),
    );
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    await act(async () => {
      await result.current.controller.run();
    });
    await waitFor(() => {
      expect(result.current.loc.pathname).toBe(
        `/projects/${PROJECT_ID}/sync/conflicts`,
      );
    });
    expect(toasts()).toHaveLength(1);
    expect(toasts()[0]).toMatchObject({ kind: "warning", duration: 0 });
  });

  it("resumes an operation found in the status after a reload, without moving the screen", async () => {
    vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
      operation({
        id: "op-9",
        result: {
          ...RESULT,
          outcome: "conflicts",
          conflicts: { files_total: 1, files_open: 1 },
        },
      }),
    );
    const { result } = setup(
      connected({
        ui_state: "syncing",
        operation: runningOperation({ id: "op-9" }),
      }),
    );
    await waitFor(() => {
      expect(toasts()).toHaveLength(1);
    });
    expect(toasts()[0]?.kind).toBe("warning");
    expect(result.current.loc.pathname).toBe(
      `/projects/${PROJECT_ID}/documents`,
    );
  });

  it("attaches to the running operation when the server says it is busy", async () => {
    vi.spyOn(gitSyncApi, "startSync").mockRejectedValue(
      new ApiError("busy", "sync_busy", 409, { operation_id: "op-7" }),
    );
    const poll = vi
      .spyOn(gitSyncApi, "getOperation")
      .mockResolvedValue(
        operation({ id: "op-7", status: "running", result: null }),
      );
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    await act(async () => {
      await result.current.controller.run();
    });
    await waitFor(() => {
      expect(poll).toHaveBeenCalledWith("op-7");
    });
    expect(toasts()).toHaveLength(0);
  });

  it("explains a failed start with the translated server error", async () => {
    vi.spyOn(gitSyncApi, "startSync").mockRejectedValue(
      new ApiError("x", "profile_required", 409),
    );
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    await act(async () => {
      await result.current.controller.run();
    });
    expect(toasts()).toHaveLength(1);
    expect(toasts()[0]).toMatchObject({
      kind: "error",
      title: "Не удалось начать синхронизацию",
    });
    expect(toasts()[0]?.message).toContain("имя и e-mail автора");
  });

  it("reports a failed operation with the translated error and a details action", async () => {
    vi.spyOn(gitSyncApi, "startSync").mockResolvedValue({
      operation_id: "op-1",
    });
    vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
      operation({
        status: "failed",
        result: null,
        error: { code: "auth_failed", detail: "denied" },
      }),
    );
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    await act(async () => {
      await result.current.controller.run();
    });
    await waitFor(() => {
      expect(toasts()).toHaveLength(1);
    });
    expect(toasts()[0]).toMatchObject({
      kind: "error",
      title: "Синхронизация не удалась",
      message: "Сервер не принял доступ. Проверь токен или ключ.",
    });
    act(() => {
      toasts()[0]?.action?.onClick();
    });
    expect(useSyncUiStore.getState().popoverOpen).toBe(true);
  });

  describe("outcome recorded on the server", () => {
    const recent = () => new Date(Date.now() - 20_000).toISOString();

    it("toasts a fresh sync once per sync id, even across mounts", async () => {
      const status = connected({
        last_sync: {
          id: "sync-1",
          at: recent(),
          outcome: "merged",
          pulled_commits: 1,
          pushed_commits: 2,
        },
      });
      const first = setup(status);
      await waitFor(() => {
        expect(toasts()).toHaveLength(1);
      });
      first.unmount();
      cleanup();
      const second = setup(status);
      await waitFor(() => {
        expect(second.result.current.controller.ui.visible).toBe(true);
      });
      expect(toasts()).toHaveLength(1);
    });

    it("stays silent about an old sync found at open", async () => {
      setup(
        connected({
          last_sync: {
            id: "sync-old",
            at: new Date(Date.now() - 3 * 3600_000).toISOString(),
            outcome: "merged",
            pulled_commits: 1,
            pushed_commits: 2,
          },
        }),
      );
      await waitFor(() => {
        expect(useSyncUiStore.getState().toastedSyncIds[PROJECT_ID]).toBe(
          "sync-old",
        );
      });
      expect(toasts()).toHaveLength(0);
    });

    it("does not toast the record of a sync it already reported from the operation", async () => {
      vi.spyOn(gitSyncApi, "startSync").mockResolvedValue({
        operation_id: "op-1",
      });
      vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(operation());
      const { result, client } = setup();
      await waitFor(() => {
        expect(result.current.controller.ui.visible).toBe(true);
      });
      await act(async () => {
        await result.current.controller.run();
      });
      await waitFor(() => {
        expect(toasts()).toHaveLength(1);
      });
      // Сервер дописал last_sync после операции.
      act(() => {
        client.setQueryData(
          gitSyncKeys.status(PROJECT_ID),
          connected({
            last_sync: {
              id: "sync-new",
              at: recent(),
              outcome: "merged",
              pulled_commits: 2,
              pushed_commits: 3,
            },
          }),
        );
      });
      await waitFor(() => {
        expect(useSyncUiStore.getState().toastedSyncIds[PROJECT_ID]).toBe(
          "sync-new",
        );
      });
      expect(toasts()).toHaveLength(1);
    });
  });

  describe("races between the status poll and the operation poll", () => {
    const record = (outcome: string) =>
      connected({
        last_sync: {
          id: "sync-new",
          at: new Date(Date.now() - 1_000).toISOString(),
          outcome,
          pulled_commits: 2,
          pushed_commits: 3,
        },
      });

    const startWithSlowOperation = async (final: GitOperation) => {
      let finish: (op: GitOperation) => void = () => undefined;
      vi.spyOn(gitSyncApi, "startSync").mockResolvedValue({
        operation_id: "op-1",
      });
      vi.spyOn(gitSyncApi, "getOperation").mockReturnValue(
        new Promise<GitOperation>((resolve) => {
          finish = resolve;
        }),
      );
      const env = setup();
      await waitFor(() => {
        expect(env.result.current.controller.ui.visible).toBe(true);
      });
      await act(async () => {
        await env.result.current.controller.run();
      });
      return { ...env, finish: () => finish(final) };
    };

    it("shows one toast when the status with last_sync arrives before the operation", async () => {
      const { client, finish } = await startWithSlowOperation(operation());
      act(() => {
        client.setQueryData(gitSyncKeys.status(PROJECT_ID), record("merged"));
      });
      await waitFor(() => {
        expect(useSyncUiStore.getState().toastedSyncIds[PROJECT_ID]).toBe(
          "sync-new",
        );
      });
      expect(toasts()).toHaveLength(0);
      act(() => {
        finish();
      });
      await waitFor(() => {
        expect(toasts()).toHaveLength(1);
      });
      expect(toasts()[0]?.action).toBeDefined();
    });

    it("does not announce a merge for a sync that ended in conflicts", async () => {
      const { client, finish } = await startWithSlowOperation(
        operation({
          result: {
            ...RESULT,
            outcome: "conflicts",
            conflicts: { files_open: 2 } as SyncResult["conflicts"],
          },
        }),
      );
      act(() => {
        client.setQueryData(
          gitSyncKeys.status(PROJECT_ID),
          record("conflicts"),
        );
      });
      await waitFor(() => {
        expect(useSyncUiStore.getState().toastedSyncIds[PROJECT_ID]).toBe(
          "sync-new",
        );
      });
      act(() => {
        finish();
      });
      await waitFor(() => {
        expect(toasts()).toHaveLength(1);
      });
      expect(toasts()[0]).toMatchObject({ kind: "warning" });
    });

    it("ignores finished operations that are not a sync of this project", async () => {
      const { client } = setup();
      await waitFor(() => {
        expect(useSyncUiStore.getState().toastedSyncIds).toBeDefined();
      });
      act(() => {
        client.setQueryData(
          gitSyncKeys.operation("clone-1"),
          operation({
            id: "clone-1",
            kind: "clone",
            project_id: null,
            status: "failed",
            result: null,
            error: { code: "remote_unreachable", detail: "" },
          }),
        );
        client.setQueryData(
          gitSyncKeys.operation("other-1"),
          operation({ id: "other-1", project_id: "other-project" }),
        );
      });
      expect(toasts()).toHaveLength(0);
    });
  });

  it("answers the palette: a request for a sync starts it", async () => {
    const start = vi
      .spyOn(gitSyncApi, "startSync")
      .mockResolvedValue({ operation_id: "op-1" });
    vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
      operation({ status: "running", result: null }),
    );
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    act(() => {
      useSyncUiStore.getState().requestCommand("sync");
    });
    await waitFor(() => {
      expect(start).toHaveBeenCalledTimes(1);
    });
    expect(useSyncUiStore.getState().command).toBeNull();
  });

  it("a run request starts the sync even where the primary action would only open details", async () => {
    const start = vi
      .spyOn(gitSyncApi, "startSync")
      .mockResolvedValue({ operation_id: "op-run" });
    vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
      operation({ id: "op-run", status: "running", result: null }),
    );
    const { result } = setup(
      connected({
        ui_state: "error",
        health: "error",
        last_error: {
          code: "git_error",
          detail: "boom",
          at: "2026-10-26T10:00:00Z",
        },
      }),
    );
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    expect(result.current.controller.ui.primary).toBe("details");
    act(() => {
      useSyncUiStore.getState().requestCommand("run");
    });
    await waitFor(() => {
      expect(start).toHaveBeenCalledTimes(1);
    });
    expect(useSyncUiStore.getState().popoverOpen).toBe(false);
  });

  it("a run request opens the popover when syncing is not possible", async () => {
    const start = vi.spyOn(gitSyncApi, "startSync");
    const { result } = setup(
      connected({
        ui_state: "blocked",
        blocked: { reason: "off_branch", required_studio: null },
      }),
    );
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    act(() => {
      useSyncUiStore.getState().requestCommand("run");
    });
    await waitFor(() => {
      expect(useSyncUiStore.getState().popoverOpen).toBe(true);
    });
    expect(start).not.toHaveBeenCalled();
  });

  it("a request for a sync in a project without a remote opens the connect dialog", async () => {
    const { result } = setup({
      ...connected(),
      connected: false,
      ui_state: "no_remote",
      remote: null,
    });
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    act(() => {
      useSyncUiStore.getState().requestCommand("sync");
    });
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toEqual({
        mode: "connect",
      });
    });
  });

  it("checks for updates by hand and says what it found", async () => {
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.controller.ui.visible).toBe(true);
    });
    useToastStore.getState().clear();
    vi.spyOn(gitSyncApi, "fetchRemote").mockResolvedValue(
      connected({ ui_state: "behind", relation: "behind", behind: 2 }),
    );
    await act(async () => {
      await result.current.controller.check();
    });
    expect(toasts()[0]?.message).toBe("В репозитории новых версий: 2");
  });
});
