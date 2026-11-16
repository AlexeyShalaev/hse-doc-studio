import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  OutcomeRuleRefSchema,
  PackOutcomeAtlasSchema,
  PackOutcomeImpactSchema,
  PackOutcomeRequestSchema,
  PackOutcomeSchema,
  PackScenarioSchema,
} from "./outcome";

// Связи внутри эталонов вычислителя, которые схема выразить не может. Те же проверки держит
// бэкенд-тест tests/unit/contract/test_pack_studio_outcome_contract.py.

const FIXTURES = join(
  import.meta.dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "contracts",
  "pack-studio",
  "fixtures",
);

const load = (schema: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, schema, `${name}.json`), "utf8"));

describe("вычислитель результата: связи в эталонах", () => {
  const outcome = PackOutcomeSchema.parse(
    load("PackOutcome", "coursework_company_cosupervisor"),
  );

  it("каждая ссылка why указывает на решение из trace", () => {
    const ids = new Set(outcome.trace.map((t) => t.id));
    const whys = [
      ...outcome.documents.flatMap((d) => d.why),
      ...outcome.points.flatMap((p) => [...p.why, ...p.route.why]),
      ...outcome.points.flatMap((p) => p.route.pairs.flatMap((x) => x.why)),
    ];
    expect(whys.filter((id) => !ids.has(id))).toEqual([]);
    expect(ids.size).toBe(outcome.trace.length);
  });

  it("решения помнят документы, которые объясняют", () => {
    const byId = new Map(outcome.trace.map((t) => [t.id, t]));
    for (const doc of outcome.documents) {
      for (const id of doc.why) {
        const subjects = byId.get(id)?.subjects ?? [];
        expect(subjects).toContainEqual({ section: "documents", id: doc.id });
      }
    }
  });

  it("дайджест совпадает с телом результата", () => {
    expect(outcome.digest.documents).toEqual(
      Object.fromEntries(outcome.documents.map((d) => [d.id, d.state])),
    );
    expect(outcome.digest.participants).toEqual(
      outcome.participants.filter((p) => p.present).map((p) => p.persona),
    );
  });

  it("атлас: таблица согласована с измерениями и исходами", () => {
    const atlas = PackOutcomeAtlasSchema.parse(
      load("PackOutcomeAtlas", "coursework"),
    );
    const outcomes = new Set(atlas.outcomes.map((o) => o.id));
    expect(atlas.rows).toHaveLength(atlas.rows_total);
    expect(atlas.outcomes).toHaveLength(atlas.outcomes_distinct);
    for (const row of atlas.rows) {
      expect(outcomes.has(row.outcome)).toBe(true);
      expect(row.key.split("|")).toHaveLength(atlas.dimensions.length);
    }
  });

  it("сводка «до и после» сходится со сценариями", () => {
    const impact = PackOutcomeImpactSchema.parse(
      load("PackOutcomeImpact", "coursework"),
    );
    const changed = impact.scenarios.filter((s) => s.status === "changed");
    expect(impact.summary.scenarios_total).toBe(impact.scenarios.length);
    expect(impact.summary.scenarios_changed).toBe(changed.length);
  });
});

describe("вычислитель результата: строгость схем", () => {
  it("лишнее поле запроса отвергается", () => {
    expect(
      PackOutcomeRequestSchema.safeParse({ state: "head", colour: "red" })
        .success,
    ).toBe(false);
    expect(PackOutcomeRequestSchema.safeParse({}).success).toBe(true);
  });

  it("правило манифеста требует место, зашитое правило требует имя", () => {
    const base = { file: null, pointer: null, builtin: null };
    expect(
      OutcomeRuleRefSchema.safeParse({ ...base, origin: "manifest" }).success,
    ).toBe(false);
    expect(
      OutcomeRuleRefSchema.safeParse({ ...base, origin: "builtin" }).success,
    ).toBe(false);
    expect(
      OutcomeRuleRefSchema.safeParse({
        ...base,
        origin: "builtin",
        builtin: "nda_gate",
      }).success,
    ).toBe(true);
  });

  it("неизвестный вид утверждения сценария отвергается", () => {
    const scenario = {
      format: 1,
      name: { ru: "x" },
      inputs: {},
      assertions: [{ kind: "item_state", point: "final" }],
    };
    expect(PackScenarioSchema.safeParse(scenario).success).toBe(false);
  });
});
