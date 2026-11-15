import { describe, expect, it } from "vitest";
import {
  fieldText,
  fieldValue,
  findingsByRule,
  getAt,
  setAt,
  typedCheck,
} from "./params";

const PARAMS = {
  check: "page_geometry",
  expected: { left_mm: 30, right_mm: 15 },
  message: { ru: "Поля", en: "Margins" },
};

describe("параметры правил проверок", () => {
  it("поля формы только у известных структурных проверок", () => {
    expect(typedCheck("structural", PARAMS)).toBe("page_geometry");
    expect(typedCheck("structural", { check: "magic" })).toBeNull();
    expect(typedCheck("regex", PARAMS)).toBeNull();
  });

  it("правка по пути не трогает чужие ключи, пустое значение убирает ключ", () => {
    const next = setAt(PARAMS, ["expected", "left_mm"], 25);
    expect(next).toEqual({
      ...PARAMS,
      expected: { left_mm: 25, right_mm: 15 },
    });
    expect(getAt(next, ["expected", "left_mm"])).toBe(25);
    const without = setAt(
      setAt(PARAMS, ["expected", "left_mm"], undefined),
      ["expected", "right_mm"],
      undefined,
    );
    expect(without).toEqual({
      check: "page_geometry",
      message: PARAMS.message,
    });
  });

  it("текст поля и число туда и обратно", () => {
    expect(fieldText([12, 14], "numbers")).toBe("12, 14");
    expect(fieldValue("12, 14", "numbers")).toEqual([12, 14]);
    expect(fieldValue("1,5", "number")).toBe(1.5);
    expect(fieldValue("", "number")).toBeUndefined();
    expect(fieldValue("abc", "number")).toBeNull();
  });

  it("находки сборки по правилам", () => {
    const map = findingsByRule([
      { rule_id: "a", severity: "err", message: "1", file: null, line: null },
      { rule_id: "a", severity: "warn", message: "2", file: "x.tex", line: 3 },
    ]);
    expect(map.get("a")).toHaveLength(2);
    expect(findingsByRule(null).size).toBe(0);
  });
});
