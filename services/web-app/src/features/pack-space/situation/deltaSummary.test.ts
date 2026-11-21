import { describe, expect, it } from "vitest";
import { COURSEWORK_COMPARE } from "@entities/pack-studio/reference";
import { changedElements, summarizeDelta } from "./deltaSummary";

describe("summarizeDelta", () => {
  it("числа по разделам из ответа сравнения", () => {
    expect(summarizeDelta(COURSEWORK_COMPARE)).toEqual({
      identical: false,
      parts: [
        { section: "participants", added: 1, changed: 0, removed: 0 },
        { section: "route", added: 3, changed: 1, removed: 2 },
      ],
    });
  });

  it("разделы без изменений не попадают в плашку", () => {
    const summary = summarizeDelta({
      ...COURSEWORK_COMPARE,
      summary: [
        { section: "documents", added: 0, changed: 0, removed: 0 },
        { section: "points", added: 0, changed: 2, removed: 0 },
      ],
    });
    expect(summary.parts.map((part) => part.section)).toEqual(["points"]);
  });

  it("результат не изменился", () => {
    expect(
      summarizeDelta({ ...COURSEWORK_COMPARE, identical: true, summary: [] }),
    ).toEqual({ identical: true, parts: [] });
    expect(
      summarizeDelta({ ...COURSEWORK_COMPARE, identical: false, summary: [] })
        .identical,
    ).toBe(true);
  });
});

describe("changedElements", () => {
  it("ключ раздел:id и знак изменения", () => {
    const map = changedElements(COURSEWORK_COMPARE);
    expect(map.get("participants:co_supervisor")).toBe("+");
    expect(map.get("route:topic-approval/step/2")).toBe("~");
    expect(map.size).toBe(
      new Set(COURSEWORK_COMPARE.changes.map((c) => `${c.section}:${c.id}`))
        .size,
    );
  });

  it("без ответа пусто", () => {
    expect(changedElements(undefined).size).toBe(0);
  });
});
