import { describe, expect, it } from "vitest";
import {
  COURSEWORK_ATLAS,
  COURSEWORK_COMPARE,
  COURSEWORK_MATRIX,
  COURSEWORK_SCENARIOS,
} from "@entities/pack-studio/reference";
import {
  EMPTY_FILTER,
  applyRowInputs,
  filterRows,
  keyOfInputs,
  miniOf,
  rowValues,
  splitKey,
  withPin,
} from "./atlas";
import {
  defaultSides,
  groupBySection,
  resolveSides,
  subjectOf,
} from "./compare";
import { cellOf, countCells, fingerprintGroups, tallyRows } from "./matrix";

const labeler = (_input: string, value: string): string => value;

describe("атлас: ключи и строки", () => {
  const atlas = COURSEWORK_ATLAS;
  const first = atlas.rows[0];

  it("ключ делится по измерениям, %7C возвращается в |", () => {
    expect(splitKey("a|b%7Cc|d")).toEqual(["a", "b|c", "d"]);
    if (!first) throw new Error("no rows");
    const values = rowValues(atlas, first);
    expect(Object.keys(values)).toEqual(atlas.dimensions.map((d) => d.input));
  });

  it("ключ по вводным совпадает с ключом строки; недостающее берётся из умолчаний", () => {
    if (!first) throw new Error("no rows");
    const values = rowValues(atlas, first);
    expect(keyOfInputs(atlas.dimensions, values)).toBe(first.key);
    const defaults = keyOfInputs(atlas.dimensions, {});
    expect(atlas.rows.some((row) => row.key === defaults)).toBe(true);
  });

  it("выбор строки без сценария пишет только отличия от умолчаний и сохраняет прочие вводные", () => {
    const row = atlas.rows.find((r) => r.key.includes("company"));
    if (!row) throw new Error("no company row");
    const inputs = applyRowInputs(atlas, row, { lang: "en", kind: "x" }, null);
    expect(inputs.supervisor).toBe("company");
    expect(inputs.lang).toBe("en");
    // Умолчание измерения не пишется.
    for (const dim of atlas.dimensions) {
      if (inputs[dim.input] !== undefined) {
        expect(inputs[dim.input]).not.toBe(dim.default);
      }
    }
  });

  it("поверх сценария значения измерений пишутся все", () => {
    if (!first) throw new Error("no rows");
    const inputs = applyRowInputs(atlas, first, {}, "company-supervisor");
    expect(Object.keys(inputs).sort()).toEqual(
      atlas.dimensions.map((d) => d.input).sort(),
    );
  });

  it("исход пересказывается цифрами по сжатому результату", () => {
    const outcome = atlas.outcomes[0];
    if (!outcome) throw new Error("no outcomes");
    const mini = miniOf(outcome.digest);
    expect(mini.documents).toBe(
      Object.values(outcome.digest.documents).filter((s) => s === "active")
        .length,
    );
    expect(mini.participants).toBe(outcome.digest.participants.length);
  });

  it("поиск, фильтр по измерению, исход и порядок", () => {
    const all = filterRows(atlas, EMPTY_FILTER, labeler);
    expect(all).toHaveLength(atlas.rows.length);
    const company = filterRows(
      atlas,
      { ...EMPTY_FILTER, query: "COMPANY" },
      labeler,
    );
    expect(company.length).toBeGreaterThan(0);
    expect(company.length).toBeLessThan(all.length);
    const byDim = filterRows(
      atlas,
      { ...EMPTY_FILTER, dims: { supervisor: "none" } },
      labeler,
    );
    expect(byDim.every((v) => v.values.supervisor === "none")).toBe(true);
    const o1 = filterRows(atlas, { ...EMPTY_FILTER, outcome: "o1" }, labeler);
    expect(o1.every((v) => v.row.outcome === "o1")).toBe(true);
    const nothing = filterRows(
      atlas,
      { ...EMPTY_FILTER, query: "zzzz" },
      labeler,
    );
    expect(nothing).toEqual([]);
  });

  it("подписи значений участвуют в поиске", () => {
    const labeled = (input: string, value: string) =>
      input === "supervisor" && value === "company" ? "Из компании" : value;
    const found = filterRows(
      atlas,
      { ...EMPTY_FILTER, query: "из компании" },
      labeled,
    );
    expect(found.length).toBeGreaterThan(0);
  });

  it("сортировка по числу строк исхода стабильная", () => {
    const sorted = filterRows(
      atlas,
      { ...EMPTY_FILTER, sort: "rows" },
      labeler,
    );
    const size = new Map(atlas.outcomes.map((o) => [o.id, o.rows]));
    for (let i = 1; i < sorted.length; i += 1) {
      const a = sorted[i - 1];
      const b = sorted[i];
      if (!a || !b) continue;
      expect(size.get(a.row.outcome) ?? 0).toBeGreaterThanOrEqual(
        size.get(b.row.outcome) ?? 0,
      );
    }
  });

  it("закрепление: добавление, замена и снятие без мутации", () => {
    const pin = { a: "1" };
    expect(withPin(pin, "b", "2")).toEqual({ a: "1", b: "2" });
    expect(withPin(pin, "a", "3")).toEqual({ a: "3" });
    expect(withPin(pin, "a", null)).toEqual({});
    expect(pin).toEqual({ a: "1" });
  });
});

describe("матрица: итоги и группы", () => {
  const rows = COURSEWORK_MATRIX.rows;

  it("итог по строкам и счётчики клеток", () => {
    const tally = tallyRows(rows, 1);
    expect(tally.total).toBe(rows.length);
    expect(tally.passed + tally.failed + tally.errors + tally.unchecked).toBe(
      rows.length,
    );
    expect(tally.broken).toBe(1);
    const cells = countCells(rows);
    expect(cells.matched + cells.changed + cells.unchecked + cells.error).toBe(
      rows.reduce((sum, row) => sum + row.cells.length, 0),
    );
  });

  it("одинаковые отпечатки в столбце получают одну букву, единичные нет", () => {
    const groups = fingerprintGroups(rows, "documents");
    const prints = rows.map((row) => cellOf(row, "documents")?.fingerprint);
    // Документы у всех сценариев курсового одни: одна группа А.
    expect(new Set(prints).size).toBe(1);
    expect(groups.get(prints[0] ?? "")).toBe("A");
    const route = fingerprintGroups(rows, "route");
    const routePrints = rows.map((row) => cellOf(row, "route")?.fingerprint);
    for (const print of new Set(routePrints)) {
      const count = routePrints.filter((p) => p === print).length;
      expect(route.has(print ?? "")).toBe(count > 1);
    }
  });
});

describe("сравнение: стороны и группировка", () => {
  const entries = COURSEWORK_SCENARIOS.scenarios;
  const screen = {
    state: "work_tree",
    scenario: "company-supervisor",
    example: null,
    inputs: { kind: "research" },
  } as const;

  it("стороны превращаются в вводные запроса", () => {
    expect(
      subjectOf({ source: { kind: "screen" }, state: null }, screen),
    ).toEqual({
      state: "work_tree",
      scenario: "company-supervisor",
      example: null,
      inputs: { kind: "research" },
    });
    expect(
      subjectOf(
        { source: { kind: "scenario", id: "a" }, state: "head" },
        screen,
      ),
    ).toEqual({ state: "head", scenario: "a" });
    expect(
      subjectOf({ source: { kind: "defaults" }, state: "base" }, screen),
    ).toEqual({ state: "base", example: null });
    expect(
      subjectOf(
        {
          source: { kind: "inputs", inputs: { kind: "project" } },
          state: null,
        },
        screen,
      ),
    ).toEqual({
      state: "work_tree",
      example: null,
      inputs: { kind: "project" },
    });
  });

  it("стороны по умолчанию: два сценария, затем до и после, затем экран и умолчания", () => {
    const two = defaultSides(entries, true);
    expect(two.left.source.kind).toBe("scenario");
    expect(two.right.source.kind).toBe("scenario");
    const git = defaultSides([], true);
    expect(git.left).toEqual({ source: { kind: "screen" }, state: "base" });
    expect(git.right).toEqual({
      source: { kind: "screen" },
      state: "work_tree",
    });
    const plain = defaultSides([], false);
    expect(plain.left.source.kind).toBe("defaults");
    expect(plain.right.source.kind).toBe("screen");
  });

  it("выбрана одна сторона: вторая подбирается к ней", () => {
    const left = {
      source: { kind: "scenario", id: "no-supervisor" },
      state: null,
    } as const;
    const sides = resolveSides(left, null, entries, false);
    expect(sides.left).toEqual(left);
    expect(sides.right.source.kind).toBe("scenario");
    if (sides.right.source.kind === "scenario") {
      expect(sides.right.source.id).not.toBe("no-supervisor");
    }
    const alone = resolveSides(left, null, [], false);
    expect(alone.right.source.kind).toBe("defaults");
  });

  it("изменения группируются по разделам в порядке контракта", () => {
    const groups = groupBySection(COURSEWORK_COMPARE.changes);
    expect(groups.map((g) => g.section)).toEqual(
      [...new Set(COURSEWORK_COMPARE.changes.map((c) => c.section))].sort(
        (a, b) =>
          [
            "documents",
            "meta",
            "forms",
            "participants",
            "points",
            "route",
            "checks",
          ].indexOf(a) -
          [
            "documents",
            "meta",
            "forms",
            "participants",
            "points",
            "route",
            "checks",
          ].indexOf(b),
      ),
    );
    expect(groups.reduce((n, g) => n + g.changes.length, 0)).toBe(
      COURSEWORK_COMPARE.changes.length,
    );
  });
});
