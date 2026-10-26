import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { gitSyncApi, NO_REMOTE_STATUS, toStatusView } from "./gitSyncApi";
import {
  SYNC_STATUS_ACTIVE_POLL_MS,
  SYNC_STATUS_IDLE_POLL_MS,
  gitSyncKeys,
  invalidateAfterSync,
  syncStatusRefetchInterval,
  useFetchRemote,
  useOperation,
  useStartSync,
  useSyncStatus,
} from "./gitSyncQueries";
import type { GitOperation, GitStatus } from "./gitSyncSchemas";

const PROJECT = "11111111-1111-4111-8111-111111111111";

const connectedStatus = (overrides: Partial<GitStatus> = {}) =>
  toStatusView({
    ...NO_REMOTE_STATUS,
    connected: true,
    ui_state: "up_to_date",
    relation: "in_sync",
    ...overrides,
  });

const makeClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });

const wrapperFor =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

describe("syncStatusRefetchInterval", () => {
  it("does not poll an older backend without sync", () => {
    expect(
      syncStatusRefetchInterval(toStatusView(NO_REMOTE_STATUS, false)),
    ).toBe(false);
  });

  it("does not poll while no repository is connected", () => {
    expect(syncStatusRefetchInterval(toStatusView(NO_REMOTE_STATUS))).toBe(
      false,
    );
  });

  it("polls slowly while connected and idle", () => {
    expect(syncStatusRefetchInterval(connectedStatus())).toBe(
      SYNC_STATUS_IDLE_POLL_MS,
    );
    expect(SYNC_STATUS_IDLE_POLL_MS).toBe(30_000);
  });

  it("polls every second while an operation runs", () => {
    const status = connectedStatus({
      ui_state: "syncing",
      operation: {
        id: "op-1",
        kind: "sync",
        phase: "fetch",
        percent: 10,
        cancellable: true,
        started_at: "2026-10-26T10:00:00Z",
      },
    });
    expect(syncStatusRefetchInterval(status)).toBe(SYNC_STATUS_ACTIVE_POLL_MS);
    expect(SYNC_STATUS_ACTIVE_POLL_MS).toBe(1_000);
  });

  it("waits for the first answer before polling", () => {
    expect(syncStatusRefetchInterval(undefined)).toBe(false);
  });
});

describe("gitSyncApi.getStatus", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("treats 404 from an older backend as no repository and marks it unsupported", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("Not Found", "unknown_error", 404),
    );
    const status = await gitSyncApi.getStatus(PROJECT);
    expect(status.supported).toBe(false);
    expect(status.ui_state).toBe("no_remote");
    expect(status.connected).toBe(false);
  });

  it("lets other failures through so the control can show them", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("boom", "git_error", 500),
    );
    await expect(gitSyncApi.getStatus(PROJECT)).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

describe("useSyncStatus polling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("re-reads every second while an operation is running and relaxes after it", async () => {
    const running = connectedStatus({
      ui_state: "syncing",
      operation: {
        id: "op-1",
        kind: "sync",
        phase: "fetch",
        percent: null,
        cancellable: true,
        started_at: "2026-10-26T10:00:00Z",
      },
    });
    const idle = connectedStatus();
    const spy = vi
      .spyOn(gitSyncApi, "getStatus")
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(running)
      .mockResolvedValue(idle);
    const client = makeClient();
    renderHook(() => useSyncStatus(PROJECT), { wrapper: wrapperFor(client) });

    await vi.advanceTimersByTimeAsync(0);
    expect(spy).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(spy).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(spy).toHaveBeenCalledTimes(3);
    // Операция закончилась: до следующего чтения проходит полминуты.
    await vi.advanceTimersByTimeAsync(10_000);
    expect(spy).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(20_000);
    expect(spy).toHaveBeenCalledTimes(4);
  });

  it("does not poll when no repository is connected", async () => {
    const spy = vi
      .spyOn(gitSyncApi, "getStatus")
      .mockResolvedValue(toStatusView(NO_REMOTE_STATUS));
    renderHook(() => useSyncStatus(PROJECT), {
      wrapper: wrapperFor(makeClient()),
    });
    await vi.advanceTimersByTimeAsync(120_000);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("does not poll in a background tab", async () => {
    const spy = vi
      .spyOn(gitSyncApi, "getStatus")
      .mockResolvedValue(connectedStatus());
    const visibility = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    renderHook(() => useSyncStatus(PROJECT), {
      wrapper: wrapperFor(makeClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(spy).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(90_000);
    expect(spy).toHaveBeenCalledTimes(1);
    visibility.mockRestore();
  });
});

describe("mutations", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("puts the answer of a fetch straight into the status cache", async () => {
    const fresh = {
      ...NO_REMOTE_STATUS,
      connected: true,
      ui_state: "behind",
      relation: "behind",
      behind: 2,
    };
    vi.spyOn(gitSyncApi, "fetchRemote").mockResolvedValue(fresh);
    const client = makeClient();
    const { result } = renderHook(() => useFetchRemote(), {
      wrapper: wrapperFor(client),
    });
    await act(async () => {
      await result.current.mutateAsync(PROJECT);
    });
    const cached = client.getQueryData<ReturnType<typeof toStatusView>>(
      gitSyncKeys.status(PROJECT),
    );
    expect(cached?.behind).toBe(2);
    expect(cached?.supported).toBe(true);
  });

  it("re-reads the status after a failed fetch, because the server stored the reason", async () => {
    vi.spyOn(gitSyncApi, "fetchRemote").mockRejectedValue(
      new ApiError("offline", "offline", 502),
    );
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useFetchRemote(), {
      wrapper: wrapperFor(client),
    });
    await act(async () => {
      await result.current.mutateAsync(PROJECT).catch(() => undefined);
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: gitSyncKeys.status(PROJECT),
    });
  });

  it("refreshes the status after starting a sync so polling speeds up", async () => {
    vi.spyOn(gitSyncApi, "startSync").mockResolvedValue({
      operation_id: "op-9",
    });
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useStartSync(), {
      wrapper: wrapperFor(client),
    });
    await act(async () => {
      await result.current.mutateAsync(PROJECT);
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: gitSyncKeys.status(PROJECT),
    });
  });
});

describe("useOperation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const operation = (status: GitOperation["status"]): GitOperation => ({
    id: "op-1",
    kind: "sync",
    project_id: PROJECT,
    status,
    phase: "push",
    percent: null,
    message: null,
    cancellable: status === "running",
    started_at: "2026-10-26T10:00:00Z",
    finished_at: status === "running" ? null : "2026-10-26T10:00:05Z",
    result: null,
    error: null,
  });

  it("polls until the operation finishes and then stops", async () => {
    const spy = vi
      .spyOn(gitSyncApi, "getOperation")
      .mockResolvedValueOnce(operation("running"))
      .mockResolvedValueOnce(operation("running"))
      .mockResolvedValue(operation("succeeded"));
    renderHook(() => useOperation("op-1"), {
      wrapper: wrapperFor(makeClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(1_000);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(spy).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(spy).toHaveBeenCalledTimes(3);
  });

  it("does nothing without an operation id", async () => {
    const spy = vi.spyOn(gitSyncApi, "getOperation");
    renderHook(() => useOperation(null), { wrapper: wrapperFor(makeClient()) });
    await vi.advanceTimersByTimeAsync(5_000);
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("invalidateAfterSync", () => {
  it("refreshes everything a merge can change, like a template update does", () => {
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    invalidateAfterSync(client, PROJECT);
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey);
    for (const root of [
      "git-sync",
      "vcs",
      "documents",
      "files",
      "template-update",
      "forms",
      "signatures",
    ]) {
      expect(keys.some((key) => key?.[0] === root)).toBe(true);
    }
    expect(
      keys.some((key) => key?.[0] === "projects" && key[2] === PROJECT),
    ).toBe(true);
  });
});

describe("useSyncStatus result", () => {
  it("renders the hook result for a resolved status", async () => {
    vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(connectedStatus());
    const { result } = renderHook(() => useSyncStatus(PROJECT), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => {
      expect(result.current.data?.ui_state).toBe("up_to_date");
    });
    vi.restoreAllMocks();
  });
});
