import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from "vitest";
import { gitSyncApi } from "@entities/git-sync";
import { buildFiles, PROJECT_ID } from "../testing/fakeConflicts";
import { setHunkChoice } from "./conflictModel";
import { DRAFT_SAVE_DEBOUNCE_MS, useConflictDrafts } from "./useConflictDrafts";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider
    client={
      new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    }
  >
    {children}
  </QueryClientProvider>
);

const session = (fingerprint = "fp-1") => ({
  id: "s",
  fingerprint,
  ours: { commit: "o", author: null, at: null, message: null },
  theirs: { commit: "t", author: null, at: null, message: null },
  base: null,
  counts: { conflict: 4, auto: 2, total: 6 },
  unresolved: 4,
  drafts_saved_at: null,
  warnings: [],
  files: buildFiles(),
});

describe("useConflictDrafts", () => {
  let save: MockInstance<typeof gitSyncApi.saveConflictDraft>;

  beforeEach(() => {
    save = vi
      .spyOn(gitSyncApi, "saveConflictDraft")
      .mockResolvedValue(undefined);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("applies a choice at once and saves it after a pause, once for a burst", async () => {
    const { result } = renderHook(
      () => useConflictDrafts(PROJECT_ID, session()),
      { wrapper },
    );
    act(() => {
      result.current.update(
        "main.tex",
        setHunkChoice(null, "k1", { choice: "mine" }),
      );
      result.current.update("main.tex", (previous) =>
        setHunkChoice(previous, "k2", { choice: "theirs" }),
      );
    });
    expect(result.current.saveState).toBe("dirty");
    expect(result.current.drafts["main.tex"]).toEqual({
      kind: "hunks",
      hunks: { k1: { choice: "mine" }, k2: { choice: "theirs" } },
    });
    expect(save).not.toHaveBeenCalled();
    await waitFor(
      () => {
        expect(result.current.saveState).toBe("saved");
      },
      { timeout: DRAFT_SAVE_DEBOUNCE_MS * 5 },
    );
    expect(save).toHaveBeenCalledTimes(1);
    expect(result.current.savedRevision).toBe(1);
  });

  it("flushes right away without waiting for the pause", async () => {
    const { result } = renderHook(
      () => useConflictDrafts(PROJECT_ID, session()),
      { wrapper },
    );
    act(() => {
      result.current.update("main.tex", { kind: "text", content: "x" });
    });
    let ok = false;
    await act(async () => {
      ok = await result.current.flush();
    });
    expect(ok).toBe(true);
    expect(save).toHaveBeenCalledTimes(1);
    expect(result.current.saveState).toBe("saved");
  });

  it("reports a failed save and keeps the choice for the next try", async () => {
    save.mockRejectedValueOnce(new Error("offline"));
    const { result } = renderHook(
      () => useConflictDrafts(PROJECT_ID, session()),
      { wrapper },
    );
    act(() => {
      result.current.update("main.tex", { kind: "text", content: "x" });
    });
    let ok = true;
    await act(async () => {
      ok = await result.current.flush();
    });
    expect(ok).toBe(false);
    expect(result.current.saveState).toBe("error");
    expect(result.current.drafts["main.tex"]).toEqual({
      kind: "text",
      content: "x",
    });
    await act(async () => {
      ok = await result.current.flush();
    });
    expect(ok).toBe(true);
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("does not write after the session was discarded", async () => {
    const { result, unmount } = renderHook(
      () => useConflictDrafts(PROJECT_ID, session()),
      { wrapper },
    );
    act(() => {
      result.current.update("main.tex", { kind: "text", content: "x" });
      result.current.discard();
    });
    unmount();
    await new Promise((resolve) =>
      setTimeout(resolve, DRAFT_SAVE_DEBOUNCE_MS + 100),
    );
    expect(save).not.toHaveBeenCalled();
  });

  it("writes what is left when the screen is closed", async () => {
    const { result, unmount } = renderHook(
      () => useConflictDrafts(PROJECT_ID, session()),
      { wrapper },
    );
    act(() => {
      result.current.update("main.tex", { kind: "text", content: "x" });
    });
    unmount();
    await waitFor(() => {
      expect(save).toHaveBeenCalledTimes(1);
    });
  });

  it("keeps the choices when the plan is rebuilt", () => {
    let current = session("fp-1");
    const { result, rerender } = renderHook(
      () => useConflictDrafts(PROJECT_ID, current),
      { wrapper },
    );
    act(() => {
      result.current.update(
        "main.tex",
        setHunkChoice(null, "k1", { choice: "mine" }),
      );
    });
    current = session("fp-2");
    rerender();
    expect(result.current.drafts["main.tex"]).toEqual({
      kind: "hunks",
      hunks: { k1: { choice: "mine" } },
    });
  });
});
