import { describe, expect, it } from "vitest";
import { languageForPath } from "./languageForPath";

describe("languageForPath", () => {
  it("picks latex for TeX-family extensions", () => {
    expect(languageForPath("vkr/vkr.tex")).toBe("latex");
    expect(languageForPath("common/hse.cls")).toBe("latex");
    expect(languageForPath("common/hse.sty")).toBe("latex");
  });

  it("picks json/yaml/html/markdown for their extensions", () => {
    expect(languageForPath("project.json")).toBe("json");
    expect(languageForPath("pack.yaml")).toBe("yaml");
    expect(languageForPath("pack.yml")).toBe("yaml");
    expect(languageForPath("slides/index.html")).toBe("html");
    expect(languageForPath("README.md")).toBe("markdown");
  });

  it("is case-insensitive", () => {
    expect(languageForPath("VKR/VKR.TEX")).toBe("latex");
    expect(languageForPath("DATA.JSON")).toBe("json");
  });

  it("falls back to plain for everything else", () => {
    expect(languageForPath("references.bib")).toBe("plain");
    expect(languageForPath("notes.txt")).toBe("plain");
    expect(languageForPath("data.csv")).toBe("plain");
  });
});
