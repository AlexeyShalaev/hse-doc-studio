import { describe, expect, it } from "vitest";
import {
  MAX_INPUTS,
  MAX_INPUT_VALUE,
  OUTCOME_DEFAULTS,
  formatSelected,
  parseOutcomeSearch,
  parseSelected,
  writeOutcomeSearch,
} from "./urlState";

const parse = (query: string) => parseOutcomeSearch(new URLSearchParams(query));

describe("состояние экрана в адресе", () => {
  it("пустой адрес даёт умолчания", () => {
    expect(parse("")).toEqual(OUTCOME_DEFAULTS);
  });

  it("читает все части адреса", () => {
    const state = parse(
      "state=head&scenario=company-supervisor&example=auto:long&mode=student&tab=rules" +
        "&i.kind=research&i.meta.manuals=%D0%9F&selected=documents:operator_manual",
    );
    expect(state).toEqual({
      state: "head",
      scenario: "company-supervisor",
      example: "auto:long",
      inputs: { kind: "research", "meta.manuals": "П" },
      mode: "student",
      selected: { section: "documents", id: "operator_manual" },
      tab: "rules",
    });
  });

  it("невалидное отбрасывается, остальное остаётся", () => {
    const state = parse(
      "state=tomorrow&scenario=../etc&mode=root&tab=x&selected=nowhere:1&i.Bad%20Key=1&i.kind=research",
    );
    expect(state).toEqual({
      ...OUTCOME_DEFAULTS,
      inputs: { kind: "research" },
    });
  });

  it("пустое и слишком длинное значение вводной отбрасывается", () => {
    const long = "я".repeat(MAX_INPUT_VALUE + 1);
    const state = parse(
      `i.empty=&i.long=${long}&i.ctl=a%00b&i.ok=${"x".repeat(MAX_INPUT_VALUE)}`,
    );
    expect(Object.keys(state.inputs)).toEqual(["ok"]);
  });

  it("вводных не больше предела сервера", () => {
    const query = Array.from(
      { length: MAX_INPUTS + 10 },
      (_, n) => `i.k${String(n)}=v`,
    ).join("&");
    expect(Object.keys(parse(query).inputs)).toHaveLength(MAX_INPUTS);
  });

  it("выбор делится по первому двоеточию", () => {
    expect(parseSelected("points:final/step/2")).toEqual({
      section: "points",
      id: "final/step/2",
    });
    expect(parseSelected("forms:ai:used")).toEqual({
      section: "forms",
      id: "ai:used",
    });
    expect(parseSelected("documents:")).toBeNull();
    expect(parseSelected(":x")).toBeNull();
    expect(parseSelected(null)).toBeNull();
  });

  it("запись кладёт только отличия от умолчаний", () => {
    const out = writeOutcomeSearch(new URLSearchParams(), {
      state: "work_tree",
      mode: "author",
      tab: "result",
      inputs: { staffing: "team2", kind: "research" },
      selected: { section: "documents", id: "report" },
    });
    expect(out.toString()).toBe(
      "selected=documents%3Areport&i.kind=research&i.staffing=team2",
    );
  });

  it("запись сохраняет чужие параметры и снимает то, что вернулось к умолчанию", () => {
    const from = new URLSearchParams(
      "file=a.yaml&mode=student&i.kind=research&scenario=x",
    );
    const out = writeOutcomeSearch(from, {
      mode: "author",
      inputs: {},
      scenario: null,
    });
    expect(out.toString()).toBe("file=a.yaml");
  });

  it("запись и чтение возвращают то же состояние", () => {
    const state = {
      ...OUTCOME_DEFAULTS,
      state: "base" as const,
      scenario: "no-supervisor",
      example: "auto:normal",
      inputs: { "answer.ai.used_ai": "yes", lang: "en" },
      mode: "student" as const,
      selected: { section: "route" as const, id: "final/step/1" },
      tab: "inputs" as const,
    };
    const params = writeOutcomeSearch(new URLSearchParams(), state);
    expect(parseOutcomeSearch(params)).toEqual(state);
    expect(formatSelected(state.selected)).toBe("route:final/step/1");
  });
});
