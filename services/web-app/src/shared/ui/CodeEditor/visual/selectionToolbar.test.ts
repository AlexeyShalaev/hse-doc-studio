import { describe, expect, it } from "vitest";
import { computeSelectionToolbarPosition } from "./selectionToolbar";

const editor = { top: 0, right: 900, bottom: 600, left: 100 };
const viewport = { viewportWidth: 1000, viewportHeight: 700 };

describe("computeSelectionToolbarPosition", () => {
  it("centres the toolbar above a selection when there is room", () => {
    expect(
      computeSelectionToolbarPosition({
        editor,
        selection: { top: 200, right: 500, bottom: 220, left: 300 },
        toolbarWidth: 160,
        toolbarHeight: 36,
        ...viewport,
      }),
    ).toEqual({ left: 320, top: 156, placement: "above" });
  });

  it("places the toolbar below a selection near the editor top", () => {
    expect(
      computeSelectionToolbarPosition({
        editor,
        selection: { top: 25, right: 500, bottom: 45, left: 300 },
        toolbarWidth: 160,
        toolbarHeight: 36,
        ...viewport,
      }),
    ).toEqual({ left: 320, top: 53, placement: "below" });
  });

  it("clamps horizontal placement to the visible editor bounds", () => {
    const left = computeSelectionToolbarPosition({
      editor,
      selection: { top: 200, right: 125, bottom: 220, left: 115 },
      toolbarWidth: 160,
      toolbarHeight: 36,
      ...viewport,
    });
    const right = computeSelectionToolbarPosition({
      editor,
      selection: { top: 200, right: 895, bottom: 220, left: 885 },
      toolbarWidth: 160,
      toolbarHeight: 36,
      ...viewport,
    });

    expect(left?.left).toBe(108);
    expect(right?.left).toBe(732);
  });

  it("returns null when the selection is outside the visible editor", () => {
    expect(
      computeSelectionToolbarPosition({
        editor,
        selection: { top: 720, right: 500, bottom: 740, left: 300 },
        toolbarWidth: 160,
        toolbarHeight: 36,
        ...viewport,
      }),
    ).toBeNull();
  });
});
