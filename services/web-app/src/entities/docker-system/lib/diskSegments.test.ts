import { describe, expect, it } from "vitest";
import { buildDiskSegments, diskCategoryColor } from "./diskSegments";

describe("buildDiskSegments", () => {
  const label = (key: string) => `L:${key}`;

  it("keeps the fixed category order, not the order by size, and drops empty ones", () => {
    const segments = buildDiskSegments(
      [
        { key: "runtime", bytes: 5 },
        { key: "ai", bytes: 100 },
        { key: "office", bytes: 0 },
        { key: "compile", bytes: 1 },
        { key: "cache", bytes: 7 },
      ],
      label,
    );
    expect(segments.map((s) => s.key)).toEqual([
      "compile",
      "ai",
      "cache",
      "runtime",
    ]);
    expect(segments[0]).toEqual({
      key: "compile",
      label: "L:compile",
      color: "var(--chart-1)",
      bytes: 1,
    });
  });

  it("puts extra categories after the known ones with their own colour", () => {
    const segments = buildDiskSegments(
      [
        { key: "runnerWorkspaces", bytes: 3, color: "var(--x)" },
        { key: "app", bytes: 2 },
        { key: "runnerBlobs", bytes: 4 },
      ],
      label,
    );
    expect(segments.map((s) => [s.key, s.color])).toEqual([
      ["app", "var(--chart-5)"],
      ["runnerWorkspaces", "var(--x)"],
      ["runnerBlobs", "var(--fg-3)"],
    ]);
  });
});

describe("diskCategoryColor", () => {
  it("paints unknown categories in neutral ink", () => {
    expect(diskCategoryColor("languagetool")).toBe("var(--chart-2)");
    expect(diskCategoryColor("dangling")).toBe("var(--fg-3)");
    expect(diskCategoryColor("other")).toBe("var(--fg-3)");
  });
});
