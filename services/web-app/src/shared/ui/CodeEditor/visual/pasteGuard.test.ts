import { describe, expect, it } from "vitest";
import { escapeLatexText, shouldEscapePaste } from "./pasteGuard";

describe("escapeLatexText", () => {
  it("escapes all LaTeX specials, backslash first", () => {
    expect(escapeLatexText("100% и K&R, #1, a_b, 2^3, x~y, $5")).toBe(
      "100\\% и K\\&R, \\#1, a\\_b, 2\\textasciicircum{}3, x\\textasciitilde{}y, \\$5",
    );
    expect(escapeLatexText("C:\\dir")).toBe("C:\\textbackslash{}dir");
  });
});

describe("shouldEscapePaste", () => {
  it("escapes plain prose containing specials", () => {
    expect(shouldEscapePaste("Готово на 100%")).toBe(true);
    expect(shouldEscapePaste("K&R и #hashtag")).toBe(true);
  });

  it("leaves LaTeX-looking clipboard alone", () => {
    expect(shouldEscapePaste("\\textbf{жирный} и 100%")).toBe(false);
    expect(shouldEscapePaste("формула $x^2$ здесь")).toBe(false);
    expect(shouldEscapePaste("\\begin{itemize}")).toBe(false);
  });

  it("skips text without specials entirely", () => {
    expect(shouldEscapePaste("Обычное предложение.")).toBe(false);
    expect(shouldEscapePaste("")).toBe(false);
  });
});
