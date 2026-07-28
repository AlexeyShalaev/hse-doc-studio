import { describe, expect, it } from "vitest";
import { escapeLatex, htmlToLatex, latexToHtml } from "./cellRichText";

const fromHtml = (html: string): string => {
  const div = document.createElement("div");
  div.innerHTML = html;
  return htmlToLatex(div);
};

describe("latexToHtml", () => {
  it("renders inline formatting and symbols", () => {
    expect(
      latexToHtml("Система \\textbf{должна} \\textit{работать} \\ldots"),
    ).toBe("Система <strong>должна</strong> <em>работать</em> …");
    expect(latexToHtml("\\underline{под} \\texttt{code}")).toBe(
      "<u>под</u> <code>code</code>",
    );
  });

  it("maps ~ to NBSP and unwraps unknown/plain groups", () => {
    expect(latexToHtml("я~хочу")).toBe("я хочу");
    expect(latexToHtml("{plain} \\unknown{kept}")).toBe("plain kept");
  });

  it("escapes HTML-significant characters and keeps escaped specials", () => {
    expect(latexToHtml("a < b & c")).toBe("a &lt; b &amp; c");
    expect(latexToHtml("100\\% \\& \\_")).toBe("100% &amp; _");
  });
});

describe("htmlToLatex", () => {
  it("serializes formatting tags to inline commands", () => {
    expect(fromHtml("Система <strong>должна</strong> <em>работать</em>")).toBe(
      "Система \\textbf{должна} \\textit{работать}",
    );
    expect(fromHtml("<b>a</b><i>b</i><u>c</u><code>d</code>")).toBe(
      "\\textbf{a}\\textit{b}\\underline{c}\\texttt{d}",
    );
  });

  it("handles inline styles from execCommand", () => {
    expect(fromHtml('<span style="font-weight: 700">bold</span>')).toBe(
      "\\textbf{bold}",
    );
    expect(fromHtml('<span style="font-style: italic">it</span>')).toBe(
      "\\textit{it}",
    );
  });

  it("escapes specials and maps NBSP to a tie", () => {
    expect(fromHtml("100% &amp; я хочу")).toBe("100\\% \\& я~хочу");
  });

  it("drops empty wrappers and treats <br>/blocks as spaces", () => {
    expect(fromHtml("<b></b>a<br>b")).toBe("a b");
    expect(fromHtml("<div>one</div><div>two</div>")).toBe("one two");
  });
});

describe("multi-format and literal specials (from adversarial review)", () => {
  it("keeps every format on a multi-styled element", () => {
    expect(fromHtml('<b style="text-decoration:underline">x</b>')).toBe(
      "\\textbf{\\underline{x}}",
    );
    expect(
      fromHtml(
        '<span style="font-weight:bold;font-style:italic;text-decoration:underline">x</span>',
      ),
    ).toBe("\\textbf{\\textit{\\underline{x}}}");
  });

  it("round-trips a literal backslash / tilde / caret", () => {
    expect(latexToHtml("a\\textbackslash{}b")).toBe("a\\b");
    expect(fromHtml(latexToHtml("a\\textbackslash{}b"))).toBe(
      "a\\textbackslash{}b",
    );
    expect(fromHtml(latexToHtml("x\\textasciicircum{}y"))).toBe(
      "x\\textasciicircum{}y",
    );
  });
});

describe("round-trip", () => {
  it("latex → html → latex is stable for formatted text", () => {
    const latex = "Текст \\textbf{жирный} и \\textit{курсив}";
    expect(fromHtml(latexToHtml(latex))).toBe(latex);
  });
});

describe("escapeLatex", () => {
  it("escapes the LaTeX specials", () => {
    expect(escapeLatex("100% & a_b {x} ~ ^")).toBe(
      "100\\% \\& a\\_b \\{x\\} \\textasciitilde{} \\textasciicircum{}",
    );
  });
});
