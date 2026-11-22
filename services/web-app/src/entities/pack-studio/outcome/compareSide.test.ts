import { describe, expect, it } from "vitest";
import { formatSide, parseSide, sameSide } from "./compareSide";

describe("сторона сравнения в адресе", () => {
  it("записывается и читается обратно для каждого источника", () => {
    for (const raw of [
      "screen",
      "defaults@head",
      "scenario:company-supervisor",
      "scenario:a.b-c@base",
      "inputs:kind=research&meta.nda=yes@work_tree",
    ]) {
      const side = parseSide(raw);
      expect(side).not.toBeNull();
      if (side) expect(formatSide(side)).toBe(raw);
    }
  });

  it("свои вводные пишутся по алфавиту", () => {
    expect(
      formatSide({
        source: {
          kind: "inputs",
          inputs: { staffing: "solo", kind: "research" },
        },
        state: null,
      }),
    ).toBe("inputs:kind=research&staffing=solo");
  });

  it("непонятное и опасное отбрасывается", () => {
    for (const raw of [
      null,
      "",
      "everything",
      "scenario:",
      "scenario:../etc",
      "inputs:Bad=1",
      "inputs:kind=",
      "inputs:kind=a%00b",
    ]) {
      expect(parseSide(raw)).toBeNull();
    }
  });

  it("неизвестное состояние в хвосте не считается состоянием", () => {
    expect(parseSide("screen@tomorrow")).toBeNull();
  });

  it("одинаковые стороны узнаются", () => {
    const a = parseSide("scenario:x@head");
    const b = parseSide("scenario:x@head");
    const c = parseSide("scenario:x");
    expect(a && b && sameSide(a, b)).toBe(true);
    expect(a && c && sameSide(a, c)).toBe(false);
  });
});
