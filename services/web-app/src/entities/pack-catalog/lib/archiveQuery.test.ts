import { describe, expect, it } from "vitest";
import { archiveQuery, isArchiveName } from "./archiveQuery";

describe("archiveQuery: поля загрузки архива строкой запроса", () => {
  it("отправляет только заданные поля, пустые пропускает", () => {
    expect(archiveQuery({ name: "packs.zip" })).toEqual({ name: "packs.zip" });
    expect(
      archiveQuery({
        name: "packs.zip",
        label: "  ",
        packsPath: "",
        replaceBuiltin: false,
      }),
    ).toEqual({ name: "packs.zip" });
  });

  it("обрезает пробелы и передаёт замену встроенного строкой true", () => {
    expect(
      archiveQuery({
        name: "packs-2026.tar.gz",
        label: " Паки кафедры ",
        packsPath: " packs ",
        replaceBuiltin: true,
      }),
    ).toEqual({
      name: "packs-2026.tar.gz",
      label: "Паки кафедры",
      packs_path: "packs",
      replace_builtin: "true",
    });
  });
});

describe("isArchiveName", () => {
  it.each([
    ["packs.zip", true],
    ["PACKS.ZIP", true],
    ["packs.tar.gz", true],
    ["packs.tgz", true],
    ["packs.tar", false],
    ["packs.rar", false],
  ])("%s: %s", (name, expected) => {
    expect(isArchiveName(name)).toBe(expected);
  });
});
