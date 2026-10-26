import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSyncUiStore } from "./useSyncUiStore";

describe("useSyncUiStore", () => {
  beforeEach(() => {
    useSyncUiStore.setState({ popoverOpen: false, toastedSyncIds: {} });
  });

  it("announces each finished sync once per project", () => {
    const { claimSyncToast } = useSyncUiStore.getState();
    expect(claimSyncToast("p1", "sync-1")).toBe(true);
    expect(claimSyncToast("p1", "sync-1")).toBe(false);
    expect(claimSyncToast("p1", "sync-2")).toBe(true);
    // Другой проект ведёт свой счёт.
    expect(claimSyncToast("p2", "sync-1")).toBe(true);
  });

  it("forgets a deleted project", () => {
    const { claimSyncToast, forgetProject } = useSyncUiStore.getState();
    claimSyncToast("p1", "sync-1");
    forgetProject("p1");
    expect(useSyncUiStore.getState().toastedSyncIds).toEqual({});
    expect(claimSyncToast("p1", "sync-1")).toBe(true);
  });

  it("toggles the popover", () => {
    const { togglePopover } = useSyncUiStore.getState();
    togglePopover();
    expect(useSyncUiStore.getState().popoverOpen).toBe(true);
    togglePopover();
    expect(useSyncUiStore.getState().popoverOpen).toBe(false);
  });
});

describe("useSyncUiStore with blocked storage", () => {
  it("does not throw when localStorage rejects writes", () => {
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("QuotaExceededError");
      });
    try {
      useSyncUiStore.setState({ toastedSyncIds: {} });
      expect(() =>
        useSyncUiStore.getState().claimSyncToast("p9", "s1"),
      ).not.toThrow();
      expect(useSyncUiStore.getState().toastedSyncIds).toEqual({ p9: "s1" });
    } finally {
      spy.mockRestore();
    }
  });
});
