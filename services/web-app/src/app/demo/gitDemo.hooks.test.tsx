import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import {
  useConnectRemote,
  useOperation,
  useStartSync,
  useSyncStatus,
} from "@entities/git-sync";
import {
  useCreateCredential,
  useCredentials,
  useProbe,
} from "@entities/git-remote";
import { useProfile, useUpdateProfile } from "@entities/profile";
import { gitDemoRoutes, resetWorld } from "./routes";

// Настоящие хуки сущностей поверх демо-транспорта: так интерфейс и будет
// работать без сервера.

const PROJECT = "44444444-4444-4444-8444-444444444444";

const makeWrapper = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
};

describe("entities over the demo transport", () => {
  beforeAll(() => {
    installDemoAdapter(apiClient, createDemoRouter(gitDemoRoutes));
  });

  beforeEach(() => {
    resetWorld("behind");
  });

  it("reads the project status", async () => {
    const { result } = renderHook(() => useSyncStatus(PROJECT), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(result.current.data?.ui_state).toBe("behind");
    });
    expect(result.current.data?.supported).toBe(true);
    expect(result.current.data?.incoming).toHaveLength(3);
  });

  it("starts a sync and follows the operation", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(
      () => ({ start: useStartSync(), status: useSyncStatus(PROJECT) }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.status.data?.ui_state).toBe("behind");
    });
    let operationId = "";
    await act(async () => {
      operationId = (await result.current.start.mutateAsync(PROJECT))
        .operation_id;
    });
    await waitFor(() => {
      expect(result.current.status.data?.ui_state).toBe("syncing");
    });
    const op = renderHook(() => useOperation(operationId), { wrapper });
    await waitFor(() => {
      expect(op.result.current.data?.status).toBe("running");
    });
  });

  it("probes, then connects with the typed address", async () => {
    resetWorld("not_connected");
    const wrapper = makeWrapper();
    const { result } = renderHook(
      () => ({
        probe: useProbe(),
        connect: useConnectRemote(),
        status: useSyncStatus(PROJECT),
      }),
      { wrapper },
    );
    let relation = "";
    await act(async () => {
      relation = (
        await result.current.probe.mutateAsync({
          url: "https://github.com/ivan/new-repo",
          project_id: PROJECT,
        })
      ).relation;
    });
    expect(relation).toBe("empty");
    await act(async () => {
      await result.current.connect.mutateAsync({
        projectId: PROJECT,
        params: {
          url: "https://github.com/ivan/new-repo",
          credential_id: null,
        },
      });
    });
    await waitFor(() => {
      expect(result.current.status.data?.ui_state).toBe("ahead");
    });
  });

  it("creates a credential and lists it without the secret", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(
      () => ({ list: useCredentials(), create: useCreateCredential() }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.list.data).toHaveLength(2);
    });
    await act(async () => {
      await result.current.create.mutateAsync({
        kind: "pat",
        label: "Новый",
        host: "gitlab.com",
        token: "glpat-SECRET",
      });
    });
    await waitFor(() => {
      expect(result.current.list.data).toHaveLength(3);
    });
    expect(JSON.stringify(result.current.list.data)).not.toContain("SECRET");
  });

  it("saves the profile and the status stops being blocked", async () => {
    resetWorld("no_profile");
    const wrapper = makeWrapper();
    const { result } = renderHook(
      () => ({
        profile: useProfile(),
        update: useUpdateProfile(),
        status: useSyncStatus(PROJECT),
      }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.status.data?.ui_state).toBe("blocked");
    });
    expect(result.current.profile.data?.is_default).toBe(true);
    await act(async () => {
      await result.current.update.mutateAsync({
        name: "Мария Орлова",
        email: "m.orlova@edu.hse.ru",
      });
    });
    await waitFor(() => {
      expect(result.current.status.data?.ui_state).toBe("ahead");
    });
    expect(result.current.profile.data?.effective_name).toBe("Мария Орлова");
  });
});
