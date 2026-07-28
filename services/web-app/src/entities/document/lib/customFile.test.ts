import { describe, expect, it } from "vitest";

import {
  classifyCustomFile,
  getCustomFileSignability,
  type CustomFileLike,
} from "./customFile";

describe("classifyCustomFile", () => {
  it("classifies a .pdf file as pdf", () => {
    expect(classifyCustomFile("thesis.pdf")).toBe("pdf");
  });

  it("is case-insensitive for the pdf extension", () => {
    expect(classifyCustomFile("THESIS.PDF")).toBe("pdf");
  });

  it.each([
    "report.doc",
    "report.docx",
    "notes.odt",
    "letter.rtf",
    "slides.ppt",
    "slides.pptx",
    "slides.odp",
    "data.xls",
    "data.xlsx",
    "data.ods",
  ])("classifies %s as convertible", (filename) => {
    expect(classifyCustomFile(filename)).toBe("convertible");
  });

  it("classifies an unrecognized extension as unknown", () => {
    expect(classifyCustomFile("archive.zip")).toBe("unknown");
  });

  it("classifies a file with no extension as unknown", () => {
    expect(classifyCustomFile("README")).toBe("unknown");
  });
});

describe("getCustomFileSignability", () => {
  it("returns template when there is no custom file", () => {
    expect(getCustomFileSignability({ custom_file: null })).toBe("template");
    expect(getCustomFileSignability(undefined)).toBe("template");
  });

  it("returns pdf when the custom file is a pdf", () => {
    const doc: CustomFileLike = { custom_file: { ext: ".pdf" } };
    expect(getCustomFileSignability(doc)).toBe("pdf");
  });

  it("returns convertible for a convertible office format", () => {
    const doc: CustomFileLike = { custom_file: { ext: ".docx" } };
    expect(getCustomFileSignability(doc)).toBe("convertible");
  });

  it("returns unsignable for an unrecognized format", () => {
    const doc: CustomFileLike = { custom_file: { ext: ".zip" } };
    expect(getCustomFileSignability(doc)).toBe("unsignable");
  });
});
