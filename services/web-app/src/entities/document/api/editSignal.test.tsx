import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api/client";
import { getLastProjectEdit, resetProjectEdits } from "@shared/lib";
import {
  useCreateDir,
  useDeleteFile,
  useMoveFile,
  usePutFile,
  useUploadFile,
} from "./fileQueries";

// Правки файлов отмечаются для автосинхронизации (features/git-sync) только после успеха записи.

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider
    client={
      new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    }
  >
    {children}
  </QueryClientProvider>
);

describe("file mutations signal an edit", () => {
  beforeEach(() => {
    resetProjectEdits();
    vi.spyOn(apiClient, "put").mockResolvedValue({ headers: {} });
    vi.spyOn(apiClient, "delete").mockResolvedValue({});
    vi.spyOn(apiClient, "post").mockResolvedValue({});
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it.each([
    [
      "save",
      () => usePutFile(),
      { projectId: "p", path: "a.tex", content: "x" },
    ],
    ["delete", () => useDeleteFile(), { projectId: "p", path: "a.tex" }],
    ["move", () => useMoveFile(), { projectId: "p", src: "a", dst: "b" }],
    ["mkdir", () => useCreateDir(), { projectId: "p", path: "d" }],
    [
      "upload",
      () => useUploadFile(),
      { projectId: "p", path: "i.png", data: new Blob(["x"]) },
    ],
  ] as const)("after a successful %s", async (_name, hook, variables) => {
    const { result } = renderHook(
      hook as () => { mutate: (v: unknown) => void },
      { wrapper },
    );

    act(() => {
      result.current.mutate(variables);
    });

    await waitFor(() => {
      expect(getLastProjectEdit("p")).not.toBeNull();
    });
  });

  it("not when the write failed", async () => {
    vi.spyOn(apiClient, "put").mockRejectedValue(new Error("disk"));
    const { result } = renderHook(() => usePutFile(), { wrapper });

    act(() => {
      result.current.mutate({ projectId: "p", path: "a.tex", content: "x" });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(getLastProjectEdit("p")).toBeNull();
  });
});
