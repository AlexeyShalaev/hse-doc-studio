import { describe, expect, it } from "vitest";
import { patchForFile, partOfPointer, readContentRoute } from "./route";

const DIR = "hse-cs-sse/templates/coursework/versions/2026.1.3";
const DOCS = ["technical_specification", "nda"];
const read = (search: string) => readContentRoute(search, DIR, DOCS);

describe("readContentRoute: что открыто по адресу", () => {
  it.each([
    ["", { kind: "none" }],
    [
      "doc=nda",
      { kind: "document", docId: "nda", segment: "text", file: null },
    ],
    [
      "doc=nda&seg=terms",
      { kind: "document", docId: "nda", segment: "terms", file: null },
    ],
    [
      "doc=nda&seg=signatures&file=nda/nda.tex",
      {
        kind: "document",
        docId: "nda",
        segment: "signatures",
        file: "nda/nda.tex",
      },
    ],
    [
      "doc=nda&seg=bogus",
      { kind: "document", docId: "nda", segment: "text", file: null },
    ],
    ["part=fields", { kind: "part", part: "fields", file: null, at: null }],
    [
      "part=files&file=hse-cs-sse%2Fpack.yaml",
      { kind: "part", part: "files", file: "hse-cs-sse/pack.yaml", at: null },
    ],
    // `part` сильнее `doc`: раздел версии не про документ.
    [
      "doc=nda&part=deadlines",
      { kind: "part", part: "deadlines", file: null, at: null },
    ],
    // Неизвестный раздел не ломает адрес: открывается документ.
    [
      "doc=nda&part=nope",
      { kind: "document", docId: "nda", segment: "text", file: null },
    ],
  ])("%s", (search, expected) => {
    expect(read(search)).toEqual(expected);
  });

  it("старый ?file=: файл документа ведёт на его «Текст»", () => {
    const file = `${DIR}/files/technical_specification/technical_specification.ru.tex`;
    expect(read(`file=${encodeURIComponent(file)}`)).toEqual({
      kind: "document",
      docId: "technical_specification",
      segment: "text",
      file,
    });
  });

  it("старый ?file=: doc.yaml это «Условия»", () => {
    const file = `${DIR}/files/nda/doc.yaml`;
    expect(read(`file=${encodeURIComponent(file)}`)).toEqual({
      kind: "document",
      docId: "nda",
      segment: "terms",
      file: null,
    });
  });

  it("старый ?file=: общие файлы и чужие пути в «Все файлы»", () => {
    const common = `${DIR}/files/common/meta.tex.j2`;
    expect(read(`file=${encodeURIComponent(common)}`)).toEqual({
      kind: "part",
      part: "files",
      file: common,
      at: null,
    });
  });

  it("старый ?file=version.yaml&at=: раздел по указателю", () => {
    const file = encodeURIComponent(`${DIR}/version.yaml`);
    expect(read(`file=${file}&at=%2Fforms%2F1`)).toEqual({
      kind: "part",
      part: "forms",
      file: null,
      at: "/forms/1",
    });
    // Без указателя на известный раздел это обычный файл.
    expect(read(`file=${file}`)).toMatchObject({ kind: "part", part: "files" });
  });
});

describe("partOfPointer", () => {
  it.each([
    ["/meta_fields/3", "fields"],
    ["/meta_groups/0", "fields"],
    ["/forms/1", "forms"],
    ["/langs", "languages"],
    ["/pack_submission/profiles/0", "deadlines"],
    ["/signatures/slots/2", "signatures"],
    ["/checks_version", "rules"],
    ["/documents/3", "documents"],
    ["/dynamic_includes/0", "documents"],
    ["/unknown/0", null],
    ["", null],
    [null, null],
  ])("%s -> %s", (pointer, part) => {
    expect(partOfPointer(pointer)).toBe(part);
  });
});

describe("patchForFile", () => {
  it("файл документа это его «Текст», манифест «Условия», остальное «Все файлы»", () => {
    const text = `${DIR}/files/nda/nda.tex`;
    expect(patchForFile(text, DIR, DOCS)).toMatchObject({
      tab: "content",
      doc: "nda",
      file: text,
    });
    expect(patchForFile(`${DIR}/files/nda/doc.yaml`, DIR, DOCS)).toMatchObject({
      doc: "nda",
      extra: { seg: "terms" },
    });
    expect(patchForFile(`${DIR}/files/common/a.tex`, DIR, DOCS)).toMatchObject({
      part: "files",
      doc: null,
    });
  });
});
