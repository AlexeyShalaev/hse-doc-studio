import { describe, expect, it } from "vitest";
import { filterEntries } from "./filterEntries";
import type { ProbeEntry } from "@entities/setup";

const dir = (name: string): ProbeEntry => ({ name, is_dir: true });
const file = (name: string): ProbeEntry => ({ name, is_dir: false });

const names = (entries: readonly ProbeEntry[]): string[] =>
  entries.map((entry) => entry.name);

describe("filterEntries", () => {
  it("показывает содержимое папки целиком, пока ничего не набрано", () => {
    const entries = [dir("Documents"), dir("Downloads"), file("notes.txt")];

    expect(filterEntries(entries, "")).toEqual(entries);
  });

  it("отдаёт копию списка — исходный ответ докера переживает много запросов подряд", () => {
    const entries = [dir("Documents"), dir("Downloads")];

    const result = filterEntries(entries, "");

    expect(result).not.toBe(entries);
    result.push(dir("Прочее"));
    expect(names(entries)).toEqual(["Documents", "Downloads"]);
  });

  it("считает запрос из одних пробелов пустым — пробел легко задеть при вводе", () => {
    const entries = [dir("Documents"), file("notes.txt")];

    expect(filterEntries(entries, "   ")).toEqual(entries);
  });

  it("не различает регистр: папки на диске названы как попало", () => {
    const entries = [dir("Documents"), dir("HSE")];

    expect(names(filterEntries(entries, "DOC"))).toEqual(["Documents"]);
    expect(names(filterEntries(entries, "hse"))).toEqual(["HSE"]);
  });

  it("не различает регистр и в кириллице", () => {
    const entries = [dir("курсовая"), dir("ДИПЛОМ")];

    expect(names(filterEntries(entries, "КУРС"))).toEqual(["курсовая"]);
    expect(names(filterEntries(entries, "диплом"))).toEqual(["ДИПЛОМ"]);
  });

  it("ставит совпадения с начала имени выше совпадений в середине", () => {
    const entries = [dir("hse-doc-studio"), dir("my-docs"), dir("documents")];

    expect(names(filterEntries(entries, "doc"))).toEqual([
      "documents",
      "hse-doc-studio",
      "my-docs",
    ]);
  });

  it("сохраняет исходный порядок внутри каждой группы", () => {
    const entries = [
      dir("docs-b"),
      dir("old-docs"),
      dir("docs-a"),
      dir("new-docs"),
    ];

    expect(names(filterEntries(entries, "docs"))).toEqual([
      "docs-b",
      "docs-a",
      "old-docs",
      "new-docs",
    ]);
  });

  it("выбрасывает всё, что не подошло", () => {
    const entries = [dir("Documents"), dir("Music"), file("readme.md")];

    expect(names(filterEntries(entries, "doc"))).toEqual(["Documents"]);
  });

  it("возвращает пустой список, когда не подошло ничего", () => {
    const entries = [dir("Documents"), dir("Music")];

    expect(filterEntries(entries, "zzz")).toEqual([]);
  });

  it("отбирает файлы наравне с папками — отбор идёт по имени, а не по типу", () => {
    const entries = [dir("Music"), file("doc-plan.md"), dir("documents")];

    expect(filterEntries(entries, "doc")).toEqual([
      file("doc-plan.md"),
      dir("documents"),
    ]);
  });

  it("ранжирует файлы и папки в одном ряду, не разделяя их", () => {
    const entries = [dir("hse-doc-studio"), file("docs.zip")];

    expect(names(filterEntries(entries, "doc"))).toEqual([
      "docs.zip",
      "hse-doc-studio",
    ]);
  });

  it("находит по куску имени с пробелами и точками", () => {
    const entries = [
      dir("Курсовая работа 2026"),
      file("отчёт v1.2.final.pdf"),
      dir("Music"),
    ];

    expect(names(filterEntries(entries, "работа 2026"))).toEqual([
      "Курсовая работа 2026",
    ]);
    expect(names(filterEntries(entries, "v1.2."))).toEqual([
      "отчёт v1.2.final.pdf",
    ]);
  });

  it("не обращает внимания на пробелы по краям запроса", () => {
    const entries = [dir("Documents"), dir("Music")];

    expect(names(filterEntries(entries, "  doc  "))).toEqual(["Documents"]);
  });
});
