import { describe, expect, it } from "vitest";
import {
  VKR_INPUTS,
  VKR_OUTCOME,
  COURSEWORK_INPUTS,
  COURSEWORK_SCENARIOS,
} from "@entities/pack-studio/reference";
import {
  baseValue,
  baselineOf,
  elementKey,
  exampleDefaultsOf,
  isInert,
  isToken,
  linkedElements,
  sameInputs,
  withValue,
} from "./inputs";

const input = (id: string) => {
  const found = VKR_INPUTS.inputs.find((item) => item.id === id);
  if (!found) throw new Error(id);
  return found;
};

describe("помощники панели «Вводные»", () => {
  it("не влияют те вводные, у которых нет разделов в affects", () => {
    expect(VKR_INPUTS.inputs.filter(isInert).map((item) => item.id)).toEqual([
      "lang",
      "variant.presentation",
    ]);
  });

  it("исходное значение: сценарий важнее умолчания, умолчание берётся у версии", () => {
    const baseline = baselineOf(
      VKR_INPUTS,
      COURSEWORK_SCENARIOS,
      "company-supervisor",
    );
    expect(baseline.example).toBe("auto:normal");
    expect(baseValue(input("supervisor"), baseline, {})).toBe("company");
    expect(baseValue(input("kind"), baseline, {})).toBe("project");
    // Набор данных задаёт часть вводных сам, сценарий его перекрывает.
    expect(baseValue(input("kind"), baseline, { kind: "research" })).toBe(
      "research",
    );
    expect(
      baseValue(input("supervisor"), baseline, { supervisor: "none" }),
    ).toBe("company");
  });

  it("сценария нет или он не разобран: исходные значения это умолчания версии", () => {
    for (const id of [null, "draft", "no-such"]) {
      const baseline = baselineOf(VKR_INPUTS, COURSEWORK_SCENARIOS, id);
      expect(baseline.scenario).toEqual({});
      expect(baseline.scenarioName).toBeNull();
    }
    expect(baselineOf(VKR_INPUTS, undefined, "x").example).toBe("auto:normal");
  });

  it("набор данных без умолчаний и неизвестный дают пустой словарь", () => {
    expect(exampleDefaultsOf(VKR_INPUTS, "auto:normal")).toEqual({});
    expect(exampleDefaultsOf(VKR_INPUTS, "examples/none")).toEqual({});
  });

  it("withValue: значение, равное исходному, убирает запись", () => {
    expect(withValue({}, "kind", "research", "project")).toEqual({
      kind: "research",
    });
    expect(
      withValue({ kind: "research" }, "kind", "project", "project"),
    ).toEqual({});
    expect(
      withValue({ kind: "research", a: "b" }, "kind", "research", "project"),
    ).toEqual({ a: "b", kind: "research" });
  });

  it("sameInputs сравнивает по значениям, порядок ключей не важен", () => {
    expect(sameInputs({ a: "1", b: "2" }, { b: "2", a: "1" })).toBe(true);
    expect(sameInputs({ a: "1" }, { a: "2" })).toBe(false);
    expect(sameInputs({ a: "1" }, {})).toBe(false);
  });

  it("isToken пропускает только простые токены словаря", () => {
    expect(isToken("team2")).toBe(true);
    expect(isToken("Программиста и оператора")).toBe(false);
    expect(isToken("a.b")).toBe(false);
  });

  it("связи вводной с элементами берутся только из трассы", () => {
    const linked = linkedElements(VKR_OUTCOME, "meta.nda").map(elementKey);
    expect(linked.length).toBeGreaterThan(0);
    const reading = VKR_OUTCOME.trace.filter((d) =>
      d.terms.some((t) => t.subject === "meta.nda"),
    );
    expect(linked).toEqual([
      ...new Set(reading.flatMap((d) => d.subjects.map(elementKey))),
    ]);
    // Вводная, которую трасса не читает, связей не имеет; результата нет: связей тоже.
    expect(linkedElements(VKR_OUTCOME, "supervisor")).toEqual([]);
    expect(linkedElements(undefined, "kind")).toEqual([]);
  });

  it("вводные курсового собраны из его результата и проходят строгую схему", () => {
    const ids = COURSEWORK_INPUTS.inputs.map((item) => item.id);
    expect(ids).toContain("meta.proposal_stage");
    expect(ids).toContain("meta.report_margins");
    expect(COURSEWORK_INPUTS.template).toBe("coursework");
  });
});
