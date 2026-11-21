import { describe, expect, it } from "vitest";
import type { OutcomeInput } from "@entities/pack-studio";
import { groupInputs, isInert, topInputs } from "./topInputs";

const input = (
  id: string,
  rules: number,
  affects: OutcomeInput["affects"] = ["documents"],
): OutcomeInput => ({
  id,
  group: "project",
  type: "select",
  label: null,
  values: [{ value: "a", label: null }],
  default: "a",
  affects,
  rules,
});

const LIST = [
  input("lang", 21, []),
  input("kind", 9),
  input("staffing", 12),
  input("nda", 1),
  input("manuals", 9),
  input("supervisor", 0, ["participants"]),
  input("variant", 0, []),
];
const ids = (list: readonly OutcomeInput[]) => list.map((item) => item.id);

describe("topInputs", () => {
  it("три условия, которые читает больше всего правил; без влияния не берём", () => {
    expect(ids(topInputs(LIST))).toEqual(["staffing", "kind", "manuals"]);
  });

  it("при равенстве порядок версии", () => {
    expect(
      ids(topInputs([input("b", 5), input("a", 5), input("c", 5)])),
    ).toEqual(["b", "a", "c"]);
  });

  it("условий меньше трёх: берём сколько есть", () => {
    expect(ids(topInputs([input("only", 2), input("inert", 9, [])]))).toEqual([
      "only",
    ]);
    expect(topInputs([])).toEqual([]);
  });

  it("условие без `affects` ничего не меняет", () => {
    expect(isInert(input("x", 5, []))).toBe(true);
    expect(isInert(input("x", 0))).toBe(false);
  });
});

describe("groupInputs", () => {
  it("полоса, окно и условия без влияния", () => {
    const groups = groupInputs(LIST, new Set());
    expect(ids(groups.shown)).toEqual(["kind", "staffing", "manuals"]);
    expect(ids(groups.more)).toEqual(["nda", "supervisor"]);
    expect(ids(groups.inert)).toEqual(["lang", "variant"]);
  });

  it("изменённое условие встаёт на полосу, а в окне остаётся на месте", () => {
    const groups = groupInputs(LIST, new Set(["nda", "lang"]));
    expect(ids(groups.shown)).toEqual(["kind", "staffing", "nda", "manuals"]);
    expect(ids(groups.more)).toEqual(["nda", "supervisor"]);
    expect(ids(groups.inert)).toEqual(["lang", "variant"]);
  });
});
