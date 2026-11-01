import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getLastProjectEdit,
  noteProjectEdit,
  resetProjectEdits,
  subscribeProjectEdits,
} from "./editActivity";

describe("editActivity", () => {
  afterEach(resetProjectEdits);

  it("remembers the last edit per project", () => {
    noteProjectEdit("a", 100);
    noteProjectEdit("b", 200);
    noteProjectEdit("a", 300);

    expect(getLastProjectEdit("a")).toBe(300);
    expect(getLastProjectEdit("b")).toBe(200);
    expect(getLastProjectEdit("c")).toBeNull();
  });

  it("tells subscribers until they unsubscribe", () => {
    const seen = vi.fn();
    const unsubscribe = subscribeProjectEdits(seen);

    noteProjectEdit("a", 100);
    unsubscribe();
    noteProjectEdit("a", 200);

    expect(seen).toHaveBeenCalledTimes(1);
    expect(seen).toHaveBeenCalledWith("a", 100);
  });
});
