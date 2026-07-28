import { describe, expect, it } from "vitest";
import { EditorSelection } from "@codemirror/state";
import { touchesSelection } from "./reveal";

describe("touchesSelection", () => {
  it("counts boundary contact on both sides", () => {
    expect(touchesSelection(EditorSelection.single(5), 5, 10)).toBe(true);
    expect(touchesSelection(EditorSelection.single(10), 5, 10)).toBe(true);
  });

  it("misses positions strictly outside", () => {
    expect(touchesSelection(EditorSelection.single(4), 5, 10)).toBe(false);
    expect(touchesSelection(EditorSelection.single(11), 5, 10)).toBe(false);
  });

  it("detects a range overlapping the construct", () => {
    expect(touchesSelection(EditorSelection.single(0, 7), 5, 10)).toBe(true);
    expect(touchesSelection(EditorSelection.single(0, 4), 5, 10)).toBe(false);
  });
});
