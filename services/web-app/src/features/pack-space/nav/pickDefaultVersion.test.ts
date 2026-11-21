import { describe, expect, it } from "vitest";
import type { PackTreeTemplate } from "@entities/pack-studio";
import { GALLERY_TREE } from "../galleryKit";
import {
  countByVersion,
  myChanges,
  pickDefaultVersion,
} from "./pickDefaultVersion";

const BASE = "hse-cs-sse/templates/coursework/versions";
const version = (id: string, released: boolean) => ({
  version: id,
  path: `${BASE}/${id}`,
  status: released ? "stable" : "beta",
  released,
  modified: false,
});
// 2026.1.1 и 2026.1.2 выпущены, 2026.1.3 и 2026.1.4 черновики; по умолчанию 2026.1.2.
const TEMPLATE: PackTreeTemplate = {
  id: "coursework",
  path: "hse-cs-sse/templates/coursework",
  name: null,
  default_version: "2026.1.2",
  versions: [
    version("2026.1.1", true),
    version("2026.1.2", true),
    version("2026.1.3", false),
    version("2026.1.4", false),
  ],
};
const IN = (v: string, file = "version.yaml") => `${BASE}/${v}/${file}`;

describe("pickDefaultVersion: версия с изменениями, потом последняя, потом умолчание", () => {
  it.each([
    ["ничего нет: версия по умолчанию", [], null, "2026.1.2"],
    ["была выпущенная версия: она", [], "2026.1.1", "2026.1.1"],
    [
      "изменения в черновике важнее последней посещённой",
      [IN("2026.1.3")],
      "2026.1.1",
      "2026.1.3",
    ],
    [
      "изменения важнее умолчания",
      [IN("2026.1.4"), IN("2026.1.4", "files/a/doc.tex")],
      null,
      "2026.1.4",
    ],
    [
      "изменения в двух версиях: та, где были",
      [IN("2026.1.3"), IN("2026.1.4")],
      "2026.1.3",
      "2026.1.3",
    ],
    [
      "изменения в двух версиях и были в третьей: самая новая из изменённых",
      [IN("2026.1.3"), IN("2026.1.4")],
      "2026.1.1",
      "2026.1.4",
    ],
    ["последней посещённой уже нет: умолчание", [], "9.9.9", "2026.1.2"],
    [
      "пути вне версии (манифест пака) не считаются изменениями",
      ["hse-cs-sse/pack.yaml", "hse-cs-sse/templates/coursework/template.yaml"],
      null,
      "2026.1.2",
    ],
    [
      "регистр путей не важен",
      [IN("2026.1.3").toUpperCase()],
      null,
      "2026.1.3",
    ],
  ])("%s", (_name, changed, last, expected) => {
    expect(pickDefaultVersion(TEMPLATE, changed, last)).toBe(expected);
  });

  it("нет версии по умолчанию: самая новая из списка", () => {
    expect(
      pickDefaultVersion({ ...TEMPLATE, default_version: "нет" }, [], null),
    ).toBe("2026.1.4");
  });

  it("у шаблона нет версий: null", () => {
    expect(
      pickDefaultVersion({ ...TEMPLATE, versions: [] }, [IN("2026.1.3")], null),
    ).toBeNull();
  });
});

describe("изменения по версиям", () => {
  it("считает файлы по каталогам версий", () => {
    const counts = countByVersion([
      IN("2026.1.3"),
      IN("2026.1.3", "files/a/doc.tex"),
      IN("2026.1.4"),
      "hse-cs-sse/pack.yaml",
    ]);
    expect([...counts.entries()].sort()).toEqual([
      [`${BASE}/2026.1.3`.toLowerCase(), 2],
      [`${BASE}/2026.1.4`.toLowerCase(), 1],
    ]);
  });

  it("myChanges: версии дерева с изменениями, в порядке дерева", () => {
    const changed = [IN("2026.1.3"), IN("2026.1.3", "x.tex"), IN("2026.1.2")];
    expect(myChanges(GALLERY_TREE, changed)).toEqual([
      {
        ref: {
          pack: "hse-cs-sse",
          template: "coursework",
          version: "2026.1.2",
        },
        files: 1,
      },
      {
        ref: {
          pack: "hse-cs-sse",
          template: "coursework",
          version: "2026.1.3",
        },
        files: 2,
      },
    ]);
    expect(myChanges(GALLERY_TREE, [])).toEqual([]);
  });
});
