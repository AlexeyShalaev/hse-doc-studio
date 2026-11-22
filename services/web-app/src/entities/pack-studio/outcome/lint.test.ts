import { describe, expect, it } from "vitest";
import type { OutcomeFinding, RuleCoverage } from "@entities/pack-studio";
import {
  NO_FILTER,
  countsOf,
  coveragePercent,
  groupFindings,
  isUncoveredRule,
  missingOutcomes,
  rulesOf,
  touches,
} from "./lint";

const finding = (
  rule_id: string,
  severity: OutcomeFinding["severity"],
  extra: Partial<OutcomeFinding> = {},
): OutcomeFinding => ({
  rule_id,
  severity,
  message: `Сообщение ${rule_id}`,
  hint: null,
  file: "version.yaml",
  pointer: null,
  line: null,
  elements: [],
  witnesses: [],
  ...extra,
});

const NONE = finding("none", "info");
const at = (index: number): OutcomeFinding => ALL[index] ?? NONE;

const ALL = [
  finding("a-rule", "warning"),
  finding("b-rule", "error", {
    elements: [{ section: "documents", id: "report" }],
  }),
  finding("a-rule", "warning", { message: "Другой текст", hint: "поправьте" }),
  finding("c-rule", "info", { file: "files/x/doc.yaml" }),
];

describe("находки: группы и фильтры (F11)", () => {
  it("уровни по порядку ошибка, предупреждение, информация; внутри по правилам", () => {
    const groups = groupFindings(ALL, NO_FILTER, null);
    expect(groups.map((g) => [g.severity, g.count])).toEqual([
      ["error", 1],
      ["warning", 2],
      ["info", 1],
    ]);
    expect(groups[1]?.rules.map((r) => [r.rule, r.items.length])).toEqual([
      ["a-rule", 2],
    ]);
  });

  it("номера находок устойчивы и не зависят от фильтра", () => {
    const all = groupFindings(ALL, NO_FILTER, null).flatMap((g) =>
      g.rules.flatMap((r) => r.items.map((i) => i.id)),
    );
    const only = groupFindings(
      ALL,
      { ...NO_FILTER, rule: "c-rule" },
      null,
    ).flatMap((g) => g.rules.flatMap((r) => r.items.map((i) => i.id)));
    expect(only).toEqual(["c-rule-3"]);
    expect(all).toContain("c-rule-3");
  });

  it("поиск без регистра по правилу, тексту, подсказке, файлу и элементу", () => {
    const find = (query: string) =>
      groupFindings(ALL, { ...NO_FILTER, query }, null).reduce(
        (sum, g) => sum + g.count,
        0,
      );
    expect(find("A-RULE")).toBe(2);
    expect(find("поправьте")).toBe(1);
    expect(find("files/x")).toBe(1);
    expect(find("documents:report")).toBe(1);
    expect(find("  ")).toBe(4);
    expect(find("нет такого")).toBe(0);
  });

  it("фильтр по выбранному элементу", () => {
    const selected = { section: "documents" as const, id: "report" };
    const groups = groupFindings(
      ALL,
      { ...NO_FILTER, selectedOnly: true },
      selected,
    );
    expect(groups).toHaveLength(1);
    expect(touches(at(1), selected)).toBe(true);
    expect(touches(at(0), selected)).toBe(false);
    expect(touches(at(1), null)).toBe(false);
    // Без выбранного элемента фильтр ничего не оставляет.
    expect(
      groupFindings(ALL, { ...NO_FILTER, selectedOnly: true }, null),
    ).toEqual([]);
  });

  it("правила со счётчиками по алфавиту", () => {
    expect(rulesOf(ALL)).toEqual([
      { rule: "a-rule", count: 2 },
      { rule: "b-rule", count: 1 },
      { rule: "c-rule", count: 1 },
    ]);
  });

  it("счётчики: необязательное поле infos считается нулём", () => {
    expect(countsOf({ errors: 1, warnings: 2 })).toEqual({
      errors: 1,
      warnings: 2,
      infos: 0,
    });
  });
});

describe("покрытие: подписи и запасные значения (F11)", () => {
  const rule = (extra: Partial<RuleCoverage>): RuleCoverage => ({
    rule: {
      origin: "manifest",
      file: "version.yaml",
      pointer: "/a",
      builtin: null,
    },
    kind: "visible_if",
    seen: [],
    scenarios: [],
    ...extra,
  });

  it("процент берётся из ответа, у старого ответа без него считается по числам", () => {
    const base = {
      scenarios: 1,
      rules_total: 8,
      rules_covered: 2,
      rules_half: 5,
      rules_uncovered: 1,
      rules: [],
    };
    expect(coveragePercent({ ...base, percent: 41.5 })).toBe(41.5);
    expect(coveragePercent(base)).toBe(25);
    expect(coveragePercent({ ...base, rules_total: 0 })).toBe(100);
  });

  it("не покрыто совсем, и каких исходов не хватает", () => {
    expect(isUncoveredRule(rule({}))).toBe(true);
    expect(isUncoveredRule(rule({ seen: ["held"] }))).toBe(false);
    expect(missingOutcomes(rule({ seen: ["held"] }))).toEqual(["not_held"]);
    expect(missingOutcomes(rule({ seen: [], possible: ["not_held"] }))).toEqual(
      ["not_held"],
    );
    // Без `possible` (старый ответ) достижимыми считаются оба исхода.
    expect(missingOutcomes(rule({ seen: ["held", "not_held"] }))).toEqual([]);
  });
});
