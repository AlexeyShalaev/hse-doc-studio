import { describe, expect, it } from "vitest";
import {
  addSlot,
  joinPrevious,
  missingSlots,
  moveSlot,
  moveStep,
  removeSlot,
  seedSteps,
  separate,
} from "./routeSteps";

const STEPS = [
  ["author"],
  ["supervisor", "co_supervisor"],
  ["academic_supervisor"],
];

describe("порядок маршрута пака", () => {
  it("слот переносится в другой шаг, опустевший шаг исчезает", () => {
    expect(moveSlot(STEPS, "author", { step: 1, newStep: false })).toEqual([
      ["supervisor", "co_supervisor", "author"],
      ["academic_supervisor"],
    ]);
  });

  it("слот встаёт отдельным шагом на место", () => {
    expect(
      moveSlot(STEPS, "co_supervisor", { step: 3, newStep: true }),
    ).toEqual([
      ["author"],
      ["supervisor"],
      ["academic_supervisor"],
      ["co_supervisor"],
    ]);
  });

  it("«с предыдущим» и «отдельно» обратны друг другу", () => {
    const joined = joinPrevious(STEPS, "academic_supervisor");
    expect(joined).toEqual([
      ["author"],
      ["supervisor", "co_supervisor", "academic_supervisor"],
    ]);
    expect(separate(joined, "academic_supervisor")).toEqual(STEPS);
    expect(joinPrevious(STEPS, "author")).toBe(STEPS);
    expect(separate(STEPS, "author")).toBe(STEPS);
  });

  it("шаги переставляются, слоты убираются и добавляются", () => {
    expect(moveStep(STEPS, 2, 0)[0]).toEqual(["academic_supervisor"]);
    expect(removeSlot(STEPS, "academic_supervisor")).toEqual(STEPS.slice(0, 2));
    expect(addSlot(STEPS, "author")).toBe(STEPS);
    expect(addSlot([["author"]], "supervisor")).toEqual([
      ["author"],
      ["supervisor"],
    ]);
  });

  it("свой порядок начинается со встроенного без слотов не из каталога", () => {
    expect(seedSteps(STEPS, ["author", "supervisor"])).toEqual([
      ["author"],
      ["supervisor"],
    ]);
    expect(missingSlots([["author"]], ["author", "supervisor"])).toEqual([
      "supervisor",
    ]);
  });
});
