import { describe, expect, it } from "vitest";
import type { PackScaffoldOptions } from "@entities/pack-studio";
import {
  defaultChoice,
  hasName,
  isPackId,
  isPackIdTaken,
  isTemplateId,
  sourceChoices,
} from "./scaffold";

const OPTIONS: PackScaffoldOptions = {
  sources: [
    {
      origin: "workspace",
      pack: "demo",
      name: { ru: "Демо" },
      license: "MIT",
      templates: [
        {
          template: "report",
          name: { ru: "Отчёт" },
          default_version: "2026.1",
          versions: [
            {
              version: "2026.1.1",
              status: "beta",
              released: false,
              default: false,
            },
            {
              version: "2026.1",
              status: "stable",
              released: true,
              default: true,
            },
          ],
        },
      ],
    },
    {
      origin: "catalog",
      pack: "hse-cs-sse",
      name: { ru: "СПИ" },
      license: "Apache-2.0",
      templates: [
        {
          template: "coursework",
          name: { ru: "КП" },
          default_version: "2026.1.6",
          versions: [
            {
              version: "2026.1.6",
              status: null,
              released: true,
              default: true,
            },
          ],
        },
      ],
    },
  ],
  taken_packs: ["demo", "hse-cs-sse"],
  maintainer: null,
  license: "Apache-2.0",
  version: "2026.1",
};

describe("pack scaffold helpers", () => {
  it("checks ids like the server", () => {
    expect(isPackId("spbu-cs")).toBe(true);
    expect(isPackId("Spbu")).toBe(false);
    expect(isPackId("a--b")).toBe(false);
    expect(isPackId("a_b")).toBe(false);
    expect(isTemplateId("vkr_2")).toBe(true);
    expect(isTemplateId("-vkr")).toBe(false);
    expect(isPackId("x".repeat(65))).toBe(false);
  });

  it("knows taken pack ids case-insensitively", () => {
    expect(isPackIdTaken(OPTIONS, "HSE-CS-SSE")).toBe(true);
    expect(isPackIdTaken(OPTIONS, "spbu")).toBe(false);
    expect(isPackIdTaken(undefined, "demo")).toBe(false);
  });

  it("flattens sources workspace first and picks the default version", () => {
    const choices = sourceChoices(OPTIONS);

    expect(
      choices.map((c) => `${c.source.origin}:${c.source.version}`),
    ).toEqual(["workspace:2026.1.1", "workspace:2026.1", "catalog:2026.1.6"]);
    expect(defaultChoice(choices)?.source.version).toBe("2026.1");
    expect(defaultChoice([])).toBeUndefined();
  });

  it("needs a name in at least one language", () => {
    expect(hasName({ ru: " ", en: "" })).toBe(false);
    expect(hasName({ ru: "", en: "Report" })).toBe(true);
  });
});
