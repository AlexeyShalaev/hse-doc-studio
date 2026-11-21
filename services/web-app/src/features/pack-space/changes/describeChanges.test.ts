import { describe, expect, it } from "vitest";
import type { PackFileChange } from "@entities/pack-studio";
import { GALLERY_REF } from "../galleryKit";
import { describeChanges, describePath } from "./describeChanges";

const V = "hse-cs-sse/templates/coursework/versions/2026.1.3";
const OLD = "hse-cs-sse/templates/coursework/versions/2026.1.2";
const file = (
  path: string,
  status: PackFileChange["status"] = "modified",
): PackFileChange => ({ path, status });

describe("describeChanges", () => {
  it("файлы одного смысла сливаются в одну строку со счётчиком", () => {
    const [group] = describeChanges(
      [
        file(`${V}/files/ts/ts.ru.tex`),
        file(`${V}/files/ts/ts.en.tex`),
        file(`${V}/files/ts/doc.yaml`),
        file(`${V}/version.yaml`),
      ],
      GALLERY_REF,
    );
    expect(group?.files).toBe(4);
    expect(group?.items.map((i) => [i.kind, i.doc, i.files])).toEqual([
      ["version", null, 1],
      ["docConditions", "ts", 1],
      ["docText", "ts", 2],
    ]);
  });

  it("смысл файла: общие части, картинки, правила проверки, прочее", () => {
    const kinds = (path: string) => describePath(path).kind;
    expect(kinds(`${V}/files/common/meta.tex.j2`)).toBe("common");
    expect(kinds(`${V}/files/assets/logo.png`)).toBe("assets");
    expect(kinds(`${V}/checks/gost.yaml`)).toBe("checks");
    expect(kinds(`${V}/files/ts/figure.png`)).toBe("docFiles");
    expect(kinds(`${V}/README.md`)).toBe("other");
    expect(kinds("hse-cs-sse/pack.yaml")).toBe("packInfo");
    expect(kinds("hse-cs-sse/templates/coursework/template.yaml")).toBe(
      "templateInfo",
    );
    expect(kinds("hse-cs-sse/templates/coursework/releases.yaml")).toBe(
      "releases",
    );
  });

  it("открытая версия первой, другие новее выше, файлы вне версий последними", () => {
    const groups = describeChanges(
      [
        file("hse-cs-sse/pack.yaml"),
        file(`${OLD}/version.yaml`),
        file(`${V}/version.yaml`),
      ],
      { ...GALLERY_REF, version: "2026.1.2" },
    );
    expect(groups.map((g) => g.version?.version ?? "outside")).toEqual([
      "2026.1.2",
      "2026.1.3",
      "outside",
    ]);
    expect(groups[2]?.pack).toBe("hse-cs-sse");
  });

  it("статус строки: все новые, все удалены, смесь это «изменено»", () => {
    const [group] = describeChanges(
      [
        file(`${V}/files/a/doc.yaml`, "added"),
        file(`${V}/files/a/a.tex`, "added"),
        file(`${V}/files/b/b.tex`, "deleted"),
        file(`${V}/files/c/c.tex`, "added"),
        file(`${V}/files/c/c.ru.tex`, "modified"),
      ],
      GALLERY_REF,
    );
    const status = (kind: string, doc: string) =>
      group?.items.find((i) => i.kind === kind && i.doc === doc)?.status;
    expect(status("docConditions", "a")).toBe("added");
    expect(status("docText", "b")).toBe("deleted");
    expect(status("docText", "c")).toBe("modified");
  });

  it("строка открывает не удалённый файл", () => {
    const [group] = describeChanges(
      [file(`${V}/files/b/b.tex`, "deleted")],
      GALLERY_REF,
    );
    expect(group?.items[0]?.path).toBeNull();
  });
});
