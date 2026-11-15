import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PackPreviewOptionsSchema } from "@entities/pack-studio";
import { documentFits, effectiveCombination, exampleOf } from "./combination";

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
