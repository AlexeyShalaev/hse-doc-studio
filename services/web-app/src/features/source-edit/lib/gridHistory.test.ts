import { describe, expect, it } from "vitest";
import {
  canRedo,
  canUndo,
  commit,
  initHistory,
  present,
  redo,
  undo,
} from "./gridHistory";

describe("history", () => {
  it("starts with a single state and nothing to undo/redo", () => {
    const history = initHistory("a");
    expect(present(history)).toBe("a");
    expect(canUndo(history)).toBe(false);
    expect(canRedo(history)).toBe(false);
  });

  it("coalesces same-key commits into one undo step", () => {
    let history = initHistory("a");
    history = commit(history, "ab", "cell:0:0");
    history = commit(history, "abc", "cell:0:0");
    expect(present(history)).toBe("abc");
    history = undo(history);
    expect(present(history)).toBe("a"); // one step reverts the whole run
    expect(canUndo(history)).toBe(false);
  });

  it("starts a new step when the key changes or is structural", () => {
    let history = initHistory("a");
    history = commit(history, "ax", "cell:0:1");
    history = commit(history, "ax+row", null);
    history = undo(history);
    expect(present(history)).toBe("ax");
    history = undo(history);
    expect(present(history)).toBe("a");
  });

  it("redoes after undo and drops the future on a fresh commit", () => {
    let history = initHistory("a");
    history = commit(history, "b", null);
    history = undo(history);
    expect(canRedo(history)).toBe(true);
    history = redo(history);
    expect(present(history)).toBe("b");

    history = undo(history);
    history = commit(history, "c", null); // diverge → future dropped
    expect(canRedo(history)).toBe(false);
    expect(present(history)).toBe("c");
  });

  it("never coalesces a null key", () => {
    let history = initHistory("a");
    history = commit(history, "b", null);
    history = commit(history, "c", null);
    history = undo(history);
    expect(present(history)).toBe("b");
  });
});
