import { describe, expect, it } from "vitest";
import type { TemplateFileOp } from "@entities/template-update";
import { countOrder, defaultResolution, sortOps } from "./templateUpdate.model";

const op = (path: string, action: string, resolutions: string[] = []) =>
  ({
    path,
    action,
    binary: false,
    doc_id: null,
    conflicts: 0,
    approximate_base: false,
    resolutions,
  }) satisfies TemplateFileOp;

describe("templateUpdate.model", () => {
  it("puts decisions first, silent updates last", () => {
    const sorted = sortOps([
      op("b.tex", "update"),
      op("z.tex", "conflict"),
      op("a.tex", "update"),
      op("m.tex", "merge"),
    ]);
    expect(sorted.map((o) => o.path)).toEqual([
      "z.tex",
      "m.tex",
      "a.tex",
      "b.tex",
    ]);
  });

  it("lists only non-empty counts in display order", () => {
    expect(countOrder({ update: 3, conflict: 1, add: 0 })).toEqual([
      ["conflict", 1],
      ["update", 3],
    ]);
  });

  it("keeps the user's file by default", () => {
    expect(defaultResolution(op("a", "conflict", ["mine", "theirs"]))).toBe(
      "mine",
    );
  });
});
