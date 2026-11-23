import { describe, expect, it } from "vitest";
import { COURSEWORK_COMPARE } from "@entities/pack-studio/reference";
import type { PackOutcomeCompare } from "@entities/pack-studio";
import { changedElements, rowKeyOf, summarizeDelta } from "./deltaSummary";

const SAMPLE = COURSEWORK_COMPARE.changes[0];
if (!SAMPLE) throw new Error("в фикстуре нет изменений");

const change = (
  symbol: "+" | "~" | "-",
  section: PackOutcomeCompare["changes"][number]["section"],
  id: string,
): PackOutcomeCompare["changes"][number] => ({
  ...SAMPLE,
  symbol,
  section,
  id,
});

describe("summarizeDelta", () => {
  it("считает строки частей центра, а не элементы сервера", () => {
    // Сервер: «Подписи» +3 ~1 −2 (шаги и пары одной точки). На экране это одна строка точки.
    expect(summarizeDelta(COURSEWORK_COMPARE)).toEqual({
      identical: false,
      parts: [
        { part: "people", added: 1, changed: 0, removed: 0 },
        { part: "signatures", added: 0, changed: 1, removed: 0 },
      ],
    });
  });

  it("пункты точек сдачи сворачиваются в строку точки; проверок в плашке нет", () => {
    // Три точки на экране: пункты добавлены и убраны в каждой, но строк всего три.
    const compare: PackOutcomeCompare = {
      ...COURSEWORK_COMPARE,
      summary: [],
      changes: [
        change("+", "points", "p1/report"),
        change("-", "points", "p1/review"),
        change("-", "points", "p1/plan"),
        change("+", "points", "p2/report"),
        change("-", "points", "p2/review"),
        change("-", "points", "p3/review"),
        change("+", "points", "p4"),
        change("-", "points", "p5"),
        change("-", "points", "p5/review"),
        change("~", "checks", "spelling"),
        change("+", "forms", "survey/email"),
        change("~", "meta", "topic"),
      ],
    };
    expect(summarizeDelta(compare)).toEqual({
      identical: false,
      parts: [
        { part: "data", added: 0, changed: 2, removed: 0 },
        { part: "deadlines", added: 1, changed: 3, removed: 1 },
      ],
    });
  });

  it("только проверки: результат на экране не изменился", () => {
    expect(
      summarizeDelta({
        ...COURSEWORK_COMPARE,
        changes: [change("~", "checks", "spelling")],
      }),
    ).toEqual({ identical: true, parts: [] });
  });

  it("результат не изменился", () => {
    expect(
      summarizeDelta({ ...COURSEWORK_COMPARE, identical: true, changes: [] }),
    ).toEqual({ identical: true, parts: [] });
  });
});

describe("rowKeyOf", () => {
  it("вложенный элемент относится к строке точки, подписей или анкеты", () => {
    expect(rowKeyOf("route:topic-approval/step/2")).toBe(
      "route:topic-approval",
    );
    expect(rowKeyOf("points:p1/report")).toBe("points:p1");
    expect(rowKeyOf("forms:survey/email")).toBe("forms:survey");
    expect(rowKeyOf("documents:report")).toBe("documents:report");
    expect(rowKeyOf("meta:topic")).toBe("meta:topic");
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
