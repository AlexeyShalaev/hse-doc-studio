import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PackPreviewOptionsSchema } from "@entities/pack-studio";
import {
  INPUTS_SOURCE,
  previewTarget,
  sameSource,
  type PreviewTargetInput,
} from "./previewRequest";

const OPTIONS = PackPreviewOptionsSchema.parse(
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../../../../contracts/pack-studio/fixtures/PackPreviewOptions/with_variants.json",
      ),
      "utf8",
    ),
  ),
);

const INPUTS = {
  lang: "ru",
  kind: "project",
  staffing: "team2",
  supervisor: "company",
  co_supervisor: "no",
  academic_supervisor: "yes",
  "meta.nda": "yes",
  "answer.ai_declaration.used_ai": "no",
  "variant.presentation": "beamer",
};

const base: PreviewTargetInput = {
  options: OPTIONS,
  document: "technical_specification",
  source: INPUTS_SOURCE,
  variantPick: null,
  inputs: INPUTS,
  example: null,
  shownExample: "auto:normal",
  scenarioLang: undefined,
};

describe("запрос предпросмотра из состояния экрана", () => {
  it("текущие вводные: переключатели версии, набор данных результата, вариант по умолчанию", () => {
    const target = previewTarget(base);
    expect(target.body).toEqual({
      documents: ["technical_specification"],
      example: "auto:normal",
      combination: {
        lang: "ru",
        kind: "project",
        staffing: "team2",
        supervisor: "company",
        co_supervisor: "no",
        academic_supervisor: "yes",
      },
      variant: "espd",
    });
    expect(target.variant).toBe("espd");
    expect(target.doc?.id).toBe("technical_specification");
  });

  it("лишние вводные (ответы анкет, поля meta) и значения вне списка в комбинацию не идут", () => {
    const target = previewTarget({
      ...base,
      inputs: { ...INPUTS, supervisor: "firm" },
    });
    expect(target.body?.combination).not.toHaveProperty(
      "answer.ai_declaration.used_ai",
    );
    expect(target.body?.combination).not.toHaveProperty("meta.nda");
    expect(target.body?.combination).not.toHaveProperty("supervisor");
  });

  it("вариант из вводной variant.<документ>, выбор человека главнее", () => {
    const presentation = { ...base, document: "presentation" };
    expect(previewTarget(presentation).variant).toBe("beamer");
    expect(
      previewTarget({ ...presentation, variantPick: "reveal" }).variant,
    ).toBe("reveal");
  });

  it("вариант, недоступный при языке, заменяется доступным", () => {
    const target = previewTarget({ ...base, variantPick: "srs-29148" });
    expect(target.variant).toBe("espd");
    const en = previewTarget({
      ...base,
      variantPick: "srs-29148",
      inputs: { ...INPUTS, lang: "en" },
    });
    expect(en.variant).toBe("srs-29148");
    expect(en.lang).toBe("en");
  });

  it("у документа без вариантов поля variant нет", () => {
    const target = previewTarget({ ...base, document: "report" });
    expect(target.body).not.toHaveProperty("variant");
    expect(target.variant).toBeNull();
  });

  it("набор данных из адреса главнее набора результата", () => {
    expect(previewTarget({ ...base, example: "auto:long" }).body?.example).toBe(
      "auto:long",
    );
  });

  it("сценарий: id без комбинации и набора, вариант только по выбору", () => {
    const scenario = {
      ...base,
      source: { kind: "scenario", id: "company-supervisor" } as const,
      scenarioLang: "ru",
    };
    expect(previewTarget(scenario).body).toEqual({
      documents: ["technical_specification"],
      scenario: "company-supervisor",
    });
    expect(
      previewTarget({ ...scenario, variantPick: "espd", example: "auto:long" })
        .body,
    ).toEqual({
      documents: ["technical_specification"],
      scenario: "company-supervisor",
      example: "auto:long",
      variant: "espd",
    });
    // Недоступный при языке сценария вариант на сервер не уходит.
    expect(
      previewTarget({ ...scenario, variantPick: "srs-29148" }).body,
    ).not.toHaveProperty("variant");
    expect(
      previewTarget({
        ...scenario,
        variantPick: "srs-29148",
        scenarioLang: "en",
      }).variant,
    ).toBe("srs-29148");
  });

  it("документа нет в опциях предпросмотра: запроса нет", () => {
    const target = previewTarget({ ...base, document: "unknown" });
    expect(target.doc).toBeNull();
    expect(target.body).toBeNull();
  });

  it("ключ запроса меняется с вводными и не меняется без них", () => {
    const a = previewTarget(base).key;
    expect(previewTarget(base).key).toBe(a);
    expect(
      previewTarget({ ...base, inputs: { ...INPUTS, kind: "research" } }).key,
    ).not.toBe(a);
  });

  it("сравнение источников", () => {
    expect(sameSource(INPUTS_SOURCE, { kind: "inputs" })).toBe(true);
    expect(
      sameSource({ kind: "scenario", id: "a" }, { kind: "scenario", id: "a" }),
    ).toBe(true);
    expect(
      sameSource({ kind: "scenario", id: "a" }, { kind: "scenario", id: "b" }),
    ).toBe(false);
    expect(sameSource(INPUTS_SOURCE, { kind: "scenario", id: "a" })).toBe(
      false,
    );
  });
});
