import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PackTreeSchema } from "../api/schemas";
import {
  ancestorsOf,
  buildFileTree,
  findVersion,
  isPackManifest,
  isTextPath,
  languageForPackPath,
  lintTargetOf,
  versionDirOf,
} from "./packPaths";

const V = "hse-cs-sse/templates/coursework/versions/2026.1.6";

const TREE = PackTreeSchema.parse(
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../../../../contracts/pack-studio/fixtures/PackTree/monorepo.json",
      ),
      "utf8",
    ),
  ),
);

describe("раскладка пака", () => {
  it("каталог версии по пути внутри неё, без учёта регистра частей раскладки", () => {
    expect(versionDirOf(`${V}/files/common/meta.tex.j2`)).toBe(V);
    expect(versionDirOf(V)).toBe(V);
    expect(
      versionDirOf("hse-cs-sse/Templates/coursework/Versions/2026.1.6/x"),
    ).toBe("hse-cs-sse/Templates/coursework/Versions/2026.1.6");
    expect(versionDirOf("hse-cs-sse/pack.yaml")).toBeNull();
    expect(
      versionDirOf("hse-cs-sse/templates/coursework/releases.yaml"),
    ).toBeNull();
  });

  it("что проверяет сервер: версия, манифест вне версии или ничего", () => {
    expect(lintTargetOf(`${V}/version.yaml`)).toBe(V);
    expect(lintTargetOf("hse-cs-sse/pack.yaml")).toBe("hse-cs-sse/pack.yaml");
    expect(
      isPackManifest("hse-cs-sse/templates/coursework/template.yaml"),
    ).toBe(true);
    expect(
      isPackManifest("hse-cs-sse/templates/coursework/releases.yaml"),
    ).toBe(true);
    expect(lintTargetOf("README.md")).toBeNull();
    expect(lintTargetOf("hse-cs-sse/notes/pack.yaml")).toBeNull();
  });

  it("грамматика редактора: .j2 по расширению под ним", () => {
    expect(languageForPackPath(`${V}/files/common/meta.tex.j2`)).toBe("latex");
    expect(languageForPackPath(`${V}/version.yaml`)).toBe("yaml");
    expect(languageForPackPath(`${V}/files/form.md.j2`)).toBe("markdown");
    expect(languageForPackPath("README")).toBe("plain");
  });

  it("картинки и шрифты не открываются в редакторе", () => {
    expect(isTextPath(`${V}/files/common/logo.png`)).toBe(false);
    expect(isTextPath(`${V}/files/fonts/a.otf`)).toBe(false);
    expect(isTextPath(`${V}/files/report/main.tex`)).toBe(true);
    expect(isTextPath("LICENSE")).toBe(true);
  });

  it("папки по пути к файлу", () => {
    expect(ancestorsOf("a/b/c.tex")).toEqual(["a", "a/b"]);
  });
});

describe("дерево", () => {
  it("иерархия из плоского списка: папки по путям, сначала папки, версии от новой", () => {
    const nodes = buildFileTree(TREE.files);
    expect(nodes.map((n) => n.path)).toEqual(["hse-cs-sse"]);
    const pack = nodes[0];
    expect(pack?.children.map((n) => n.name)).toEqual([
      "templates",
      "pack.yaml",
    ]);
    const versions = pack?.children[0]?.children[0]?.children.find(
      (n) => n.name === "versions",
    );
    expect(versions?.children.map((n) => n.name)).toEqual([
      "2026.1.6",
      "2026.1.5",
    ]);
    const released = versions?.children[1]?.children[0];
    expect(released?.readOnly).toBe("version_released");
  });

  it("версия файла из дерева: статус и выпущенность", () => {
    expect(findVersion(TREE, `${V}/version.yaml`)).toEqual({
      packId: "hse-cs-sse",
      templateId: "coursework",
      version: expect.objectContaining({
        version: "2026.1.6",
        released: false,
        status: "beta",
      }) as unknown,
    });
    expect(findVersion(TREE, "hse-cs-sse/pack.yaml")).toBeNull();
  });
});
