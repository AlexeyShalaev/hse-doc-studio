import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PackPreviewOptionsSchema } from "@entities/pack-studio";
import {
  documentFits,
  effectiveCombination,
  effectiveVariant,
  exampleOf,
  variantFits,
} from "./combination";

const OPTIONS = PackPreviewOptionsSchema.parse(
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../../../../contracts/pack-studio/fixtures/PackPreviewOptions/coursework.json",
      ),
      "utf8",
    ),
  ),
);

describe("комбинация предпросмотра", () => {
  it("без выбора совпадает с комбинацией сервера для набора по умолчанию", () => {
    const example = exampleOf(OPTIONS, null);
    expect(example?.id).toBe("approval-gate");
    expect(effectiveCombination(OPTIONS, example, {})).toEqual(
      OPTIONS.combination,
    );
  });

  it("выбор человека важнее набора, чужое значение отбрасывается", () => {
    const example = exampleOf(OPTIONS, "approval-gate");
    const combination = effectiveCombination(OPTIONS, example, {
      lang: "en",
      supervisor: "nobody",
    });
    expect(combination.lang).toBe("en");
    expect(combination.supervisor).toBe("university");
  });

  it("документ вне вида работы не подходит", () => {
    const proposal = OPTIONS.documents[0];
    if (!proposal) throw new Error("нет документа");
    expect(documentFits(proposal, { kind: "project", staffing: "solo" })).toBe(
      true,
    );
    expect(documentFits(proposal, { kind: "research", staffing: "solo" })).toBe(
      false,
    );
  });
});

const VARIANTS = PackPreviewOptionsSchema.parse(
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
const doc = (id: string) => {
  const found = VARIANTS.documents.find((d) => d.id === id);
  if (!found) throw new Error(`нет документа ${id}`);
  return found;
};

describe("вариант документа в предпросмотре", () => {
  it("вариант для одного языка доступен только в нём", () => {
    const srs = doc("technical_specification").variants?.[1];
    if (!srs) throw new Error("нет варианта");
    expect(variantFits(srs, "en")).toBe(true);
    expect(variantFits(srs, "ru")).toBe(false);
    const espd = doc("technical_specification").variants?.[0];
    if (!espd) throw new Error("нет варианта");
    expect(variantFits(espd, "ru")).toBe(true);
  });

  it("по умолчанию вариант документа, выбор человека важнее", () => {
    expect(effectiveVariant(doc("presentation"), undefined, "ru")).toBe("pptx");
    expect(effectiveVariant(doc("presentation"), "beamer", "ru")).toBe(
      "beamer",
    );
    expect(effectiveVariant(doc("presentation"), "nope", "ru")).toBe("pptx");
  });

  it("выбор недоступного при языке варианта заменяется доступным", () => {
    const spec = doc("technical_specification");
    expect(effectiveVariant(spec, "srs-29148", "en")).toBe("srs-29148");
    expect(effectiveVariant(spec, "srs-29148", "ru")).toBe("espd");
  });

  it("у документа без вариантов и у прежнего сервера вариант не выбирается", () => {
    expect(effectiveVariant(doc("report"), undefined, "ru")).toBeNull();
    const legacy = {
      id: "x",
      name: { ru: "X" },
      kinds: [],
      staffing: [],
    };
    expect(effectiveVariant(legacy, "beamer", "ru")).toBeNull();
  });
});
