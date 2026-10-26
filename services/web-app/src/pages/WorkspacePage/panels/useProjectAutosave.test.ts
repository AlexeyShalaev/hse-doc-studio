import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPendingSaves } from "@shared/lib/pendingSaves";

const mutate = vi.fn();
const mutateAsync = vi.fn();

vi.mock("@entities/project", () => ({
  useUpdateProject: () => ({ mutate, mutateAsync }),
}));

import { useProjectAutosave } from "./useProjectAutosave";

const project = { id: "p1", name: "Курсовая" } as Parameters<
  typeof useProjectAutosave
>[0];

describe("useProjectAutosave and pending saves", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mutate.mockReset();
    mutateAsync.mockReset().mockResolvedValue(undefined);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("writes debounced edits when an operation flushes pending saves, and waits for the answer", async () => {
    const { result } = renderHook(() => useProjectAutosave(project));
    act(() => {
      result.current.patch({ name: "Новое имя" });
    });
    expect(mutate).not.toHaveBeenCalled();

    const flushed = await flushPendingSaves();

    expect(flushed).toEqual({ total: 1, failed: 0 });
    expect(mutateAsync).toHaveBeenCalledWith({
      id: "p1",
      data: { name: "Новое имя" },
    });
    // The debounce timer must not send the same edit a second time.
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(mutate).not.toHaveBeenCalled();
  });

  it("does nothing when there is nothing to save", async () => {
    renderHook(() => useProjectAutosave(project));
    expect(await flushPendingSaves()).toEqual({ total: 1, failed: 0 });
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("reports a failed write to the caller", async () => {
    mutateAsync.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useProjectAutosave(project));
    act(() => {
      result.current.patch({ name: "x" });
    });
    expect(await flushPendingSaves()).toEqual({ total: 1, failed: 1 });
  });

  it("unregisters on unmount", async () => {
    const { unmount } = renderHook(() => useProjectAutosave(project));
    unmount();
    expect(await flushPendingSaves()).toEqual({ total: 0, failed: 0 });
  });
});
