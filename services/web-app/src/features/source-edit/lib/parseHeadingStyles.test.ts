import { describe, expect, it } from "vitest";
import {
  findHeadingStyleInputs,
  findLatexInputTargets,
  parseHeadingStyles,
} from "./parseHeadingStyles";

describe("parseHeadingStyles", () => {
  it("maps titlesec heading commands to renderer levels", () => {
    const source = String.raw`
      \titleformat{\chapter}{\centering\Huge}{Chapter}{1em}{}
      \titleformat{\section}{\raggedleft\Large}{Section}{1em}{}
      \titleformat{\subsection}{\raggedright\large}{Subsection}{1em}{}
      \titleformat{\subsubsection}{\centering}{Subsubsection}{1em}{}
      \titleformat{\paragraph}{\raggedright}{Paragraph}{1em}{}
    `;

    expect(parseHeadingStyles(source)).toEqual({
      1: "center",
      2: "right",
      3: "left",
      4: "center",
      5: "left",
    });
  });

  it("supports an optional shape, multiline input, and balanced braces", () => {
    const source = String.raw`
      \titleformat
        { \section }
        [block]
        {
          \normalfont
          \color{blue}
          {\fontfamily{ptm}\selectfont}
          \centering
        }
        {\thesection}
        {1em}
        {}
    `;

    expect(parseHeadingStyles(source)).toEqual({ 2: "center" });
  });

  it("maps subparagraph to renderer level five", () => {
    expect(
      parseHeadingStyles(
        String.raw`\titleformat{\subparagraph}[runin]{\raggedleft}{}{0pt}{}`,
      ),
    ).toEqual({ 5: "right" });
  });

  it("ignores comments, escaped delimiters, and alignment in later arguments", () => {
    const source = String.raw`
      % \titleformat{\chapter}{\centering}{}{}{}
      \titleformat{\section}{\bfseries\{literal\}}{\centering}{1em}{\raggedleft}
      \titleformat{\subsection}{
        \bfseries % \centering is disabled
        \raggedright
      }{}{}{}
    `;

    expect(parseHeadingStyles(source)).toEqual({ 3: "left" });
  });

  it("uses the last alignment command and the last declaration", () => {
    const source = String.raw`
      \titleformat{\section}{\raggedright\centering}{}{}{}
      \titleformat{\section}{\raggedleft}{}{}{}
      \titleformat{\paragraph}{\centering}{}{}{}
      \titleformat{\subparagraph}{\raggedright}{}{}{}
    `;

    expect(parseHeadingStyles(source)).toEqual({ 2: "right", 5: "left" });
  });

  it("clears an earlier explicit alignment when a level is redefined", () => {
    const source = String.raw`
      \titleformat{\section}{\centering\Large}{}{}{}
      \titleformat{\section}{\Large\bfseries}{}{}{}
    `;

    expect(parseHeadingStyles(source)).toEqual({});
  });

  it("skips malformed and unrelated declarations without throwing", () => {
    const source = String.raw`
      \titleformat{\unknown}{\centering}{}{}{}
      \titleformatExtra{\section}{\centering}{}{}{}
      \titleformat\section{\centering}{}{}{}
      \titleformat{\subsection}[broken
    `;

    expect(parseHeadingStyles(source)).toEqual({});
  });
});

describe("findHeadingStyleInputs", () => {
  it("returns only real direct preamble/style inputs in source order", () => {
    const source = String.raw`
      % \input{commented/styles}
      \input {../common/preamble}
      \input{../common/commands}
      \include{../common/styles.tex}
      \input{../common/styles.tex}
    `;

    expect(findHeadingStyleInputs(source)).toEqual([
      "../common/preamble",
      "../common/styles.tex",
    ]);
  });
});

describe("findLatexInputTargets", () => {
  it("returns real inputs, ignores comments, and removes exact duplicates", () => {
    const source = String.raw`
      % \input{ignored}
      \input {../common/change_log}
      \include{chapter-one.tex}
      \input bare-fragment.tex
      \subfile{appendices/a}
      \input\dynamicTarget
      \input{../common/change_log}
      text \input{inline-fragment}
    `;

    expect(findLatexInputTargets(source)).toEqual([
      "../common/change_log",
      "chapter-one.tex",
      "bare-fragment.tex",
      "appendices/a",
      "inline-fragment",
    ]);
  });
});
