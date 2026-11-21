import { describe, expect, it } from "vitest";
import type { PackTreePack } from "@entities/pack-studio";
import { GALLERY_TREE } from "../galleryKit";
import { refForPack, refForTemplate } from "./targets";

const BASE = "hse-cs-sse/templates/coursework/versions";
const [PACK] = GALLERY_TREE.packs;
const [TEMPLATE] = PACK?.templates ?? [];
if (!PACK || !TEMPLATE) throw new Error("в дереве-фикстуре нет шаблона");
const none = () => null;

const second: PackTreePack = {
  id: "msc",
  path: "msc",
  name: null,
  templates: [
    {
      id: "empty",
      path: "msc/templates/empty",
      name: null,
      default_version: "",
      versions: [],
    },
    {
      id: "thesis",
      path: "msc/templates/thesis",
      name: null,
      default_version: "1.0.0",
      versions: [
        {
          version: "1.0.0",
          path: "msc/templates/thesis/versions/1.0.0",
          status: "stable",
          released: true,
          modified: false,
        },
        {
          version: "1.0.1",
          path: "msc/templates/thesis/versions/1.0.1",
          status: "beta",
          released: false,
          modified: false,
        },
      ],
    },
  ],
};

describe("переход по крошкам не теряет работу", () => {
  it("смена шаблона: версия с изменениями, а не по умолчанию", () => {
    expect(
      refForTemplate(PACK, TEMPLATE, [`${BASE}/2026.1.3/version.yaml`], none),
    ).toEqual({
      pack: "hse-cs-sse",
      template: "coursework",
      version: "2026.1.3",
    });
    expect(refForTemplate(PACK, TEMPLATE, [], none)?.version).toBe("2026.1.2");
  });

  it("смена шаблона: версия, где были в прошлый раз", () => {
    expect(refForTemplate(PACK, TEMPLATE, [], () => "2026.1.3")?.version).toBe(
      "2026.1.3",
    );
  });

  it("смена пака: шаблон с изменениями, иначе первый, у которого есть версии", () => {
    expect(refForPack(second, [], none)).toEqual({
      pack: "msc",
      template: "thesis",
      version: "1.0.0",
    });
    expect(
      refForPack(second, ["msc/templates/thesis/versions/1.0.1/a.tex"], none)
        ?.version,
    ).toBe("1.0.1");
  });

  it("в паке нет шаблонов с версиями: переходить некуда", () => {
    expect(refForPack({ ...second, templates: [] }, [], none)).toBeNull();
    const [empty] = second.templates;
    expect(
      refForPack({ ...second, templates: empty ? [empty] : [] }, [], none),
    ).toBeNull();
  });
});
