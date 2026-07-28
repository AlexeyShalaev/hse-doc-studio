import { describe, expect, it } from "vitest";
import { resolveDocRelativePath } from "./resolveDocRelativePath";

describe("resolveDocRelativePath", () => {
  it("resolves ../ against the document directory and appends .tex", () => {
    expect(resolveDocRelativePath("tz/tz.tex", "../common/change_log")).toBe(
      "common/change_log.tex",
    );
    expect(resolveDocRelativePath("vkr/vkr.tex", "preamble")).toBe(
      "vkr/preamble.tex",
    );
  });

  it("keeps explicit extensions and handles ./ segments", () => {
    expect(resolveDocRelativePath("tz/tz.tex", "./img/schema.png")).toBe(
      "tz/img/schema.png",
    );
  });

  it("returns null when the path escapes the project root", () => {
    expect(resolveDocRelativePath("tz/tz.tex", "../../outside")).toBe(null);
  });

  it("rejects absolute, dynamic, URL and pipe input targets", () => {
    expect(resolveDocRelativePath("tz/tz.tex", "/etc/passwd")).toBe(null);
    expect(resolveDocRelativePath("tz/tz.tex", "C:/temp/a.tex")).toBe(null);
    expect(resolveDocRelativePath("tz/tz.tex", "https://example.test/a")).toBe(
      null,
    );
    expect(resolveDocRelativePath("tz/tz.tex", "\\dynamicTarget")).toBe(null);
    expect(resolveDocRelativePath("tz/tz.tex", "|shell-command")).toBe(null);
  });

  it("works for documents at the project root", () => {
    expect(resolveDocRelativePath("main.tex", "chapters/intro")).toBe(
      "chapters/intro.tex",
    );
  });
});
