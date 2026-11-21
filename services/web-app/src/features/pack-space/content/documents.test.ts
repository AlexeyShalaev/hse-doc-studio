import { describe, expect, it } from "vitest";
import { CONTENT_MODEL, CONTENT_VERSION_DIR } from "./fixtures";
import {
  fileLabel,
  resolveDocumentFile,
  textFilesOf,
  toContentDocuments,
} from "./documents";

const DIR = CONTENT_VERSION_DIR;
const docs = (lang: string) => toContentDocuments(CONTENT_MODEL, DIR, lang);
const byId = (id: string, lang = "ru") => {
  const found = docs(lang).find((doc) => doc.id === id);
  if (!found) throw new Error(id);
  return found;
};

const first = <T>(items: T[]): T => {
  const item = items[0];
  if (item === undefined) throw new Error("пусто");
  return item;
};

describe("toContentDocuments", () => {
  it("название на языке интерфейса, группа, манифест, основной файл", () => {
    expect(byId("technical_specification")).toMatchObject({
      name: "Техническое задание",
      group: "espd",
      manifestPath: `${DIR}/files/technical_specification/doc.yaml`,
      mainFile: "technical_specification/technical_specification.tex",
    });
    expect(byId("technical_specification", "en").name).toBe(
      "Statement of Work",
    );
  });

  it("пути файлов становятся полными, порядок как в версии", () => {
    expect(byId("nda").files).toEqual([
      { path: `${DIR}/files/nda/nda.tex`, bare: "nda/nda.tex", lang: "" },
    ]);
    expect(docs("ru").map((doc) => doc.id)[0]).toBe("technical_specification");
  });

  it("запись без названия называется по id; без doc.yaml путь строится", () => {
    const model = {
      ...CONTENT_MODEL,
      documents: [
        { id: "legacy", manifest: null, data: {}, files: [], references: [] },
      ],
    };
    expect(toContentDocuments(model, DIR, "ru")).toEqual([
      {
        id: "legacy",
        name: "legacy",
        group: null,
        manifestPath: `${DIR}/files/legacy/doc.yaml`,
        files: [],
        mainFile: null,
      },
    ]);
  });
});

describe("resolveDocumentFile", () => {
  const ts = byId("technical_specification");
  const TS = `${DIR}/files/technical_specification`;
  const pick = (file: string | null, lang = "ru") =>
    resolveDocumentFile(ts, file, lang, DIR)?.path;

  it("без file: основной файл на языке интерфейса, иначе на другом", () => {
    expect(pick(null, "ru")).toBe(`${TS}/technical_specification.ru.tex`);
    expect(pick(null, "en")).toBe(`${TS}/technical_specification.en.tex`);
    expect(pick(null, "de")).toBe(`${TS}/technical_specification.ru.tex`);
  });

  it("`source_file` из «Результата» (без языка) даёт редакцию на языке интерфейса", () => {
    expect(
      pick("technical_specification/technical_specification.tex", "en"),
    ).toBe(`${TS}/technical_specification.en.tex`);
  });

  it("полный путь и путь от files/ открывают именно этот файл", () => {
    const en = `${TS}/technical_specification.en.tex`;
    expect(pick(en, "ru")).toBe(en);
    expect(
      pick("technical_specification/technical_specification.en.tex", "ru"),
    ).toBe(en);
  });

  it("неизвестный файл: основной; документ без текстовых файлов: ничего", () => {
    expect(pick("nope/nope.tex")).toBe(`${TS}/technical_specification.ru.tex`);
    const slides = byId("presentation");
    expect(textFilesOf(slides)).toEqual([]);
    expect(resolveDocumentFile(slides, null, "ru", DIR)).toBeNull();
  });

  it("подпись файла: имя без языкового кода и язык", () => {
    expect(fileLabel(first(ts.files))).toMatch(
      /^technical_specification\.tex · (ru|en)$/,
    );
    expect(fileLabel(first(byId("nda").files))).toBe("nda.tex");
  });
});
