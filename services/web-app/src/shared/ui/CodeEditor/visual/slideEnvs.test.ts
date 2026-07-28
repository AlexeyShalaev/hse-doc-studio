import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { visualConfigFacet } from "./config";
import { buildInlineDecorations, createInlineSink } from "./inlineDecorations";
import { SlideHeaderWidget } from "./widgets";

const mkState = (doc: string, anchor: number): EditorState => {
  const state = EditorState.create({
    doc,
    selection: EditorSelection.single(anchor),
    extensions: [
      latex(),
      visualConfigFacet.of({
        macros: {},
        showComments: false,
        hintPrefixes: [],
        highlightEnvs: [],
        headingAlignments: {},
        embeddedInputBasenames: [],
      }),
    ],
  });
  ensureSyntaxTree(state, doc.length, 5000);
  return state;
};

const sinkOf = (doc: string, anchor: number) => {
  const sink = createInlineSink();
  buildInlineDecorations(mkState(doc, anchor), 0, doc.length, sink);
  return sink;
};

const slideHeads = (doc: string, anchor: number): SlideHeaderWidget[] =>
  sinkOf(doc, anchor)
    .deco.map((r) => (r.value.spec as { widget?: unknown }).widget)
    .filter((w): w is SlideHeaderWidget => w instanceof SlideHeaderWidget);

const TWO_SLIDES = String.raw`\begin{frame}{Актуальность}
\begin{itemize}
\item раз
\end{itemize}
\end{frame}
\begin{frame}{Цель работы}
\item два
\end{frame}`;

describe("beamer frame / block", () => {
  it("renders a frame as a titled slide header with the slide number", () => {
    const heads = slideHeads(TWO_SLIDES, TWO_SLIDES.indexOf("раз"));
    const first = heads.find((h) => h.title === "Актуальность");
    expect(first).toBeDefined();
    expect(first?.badge).toBe("Слайд 1");
  });

  it("numbers the second frame «Слайд 2»", () => {
    const heads = slideHeads(TWO_SLIDES, TWO_SLIDES.indexOf("два"));
    const second = heads.find((h) => h.title === "Цель работы");
    expect(second?.badge).toBe("Слайд 2");
  });

  it("ignores a \\begin{frame} inside a comment when numbering", () => {
    const doc =
      "% пример: \\begin{frame}{Демо}\n\\begin{frame}{Первый}\nтело\n\\end{frame}";
    const head = slideHeads(doc, doc.indexOf("тело"))[0];
    expect(head?.title).toBe("Первый");
    expect(head?.badge).toBe("Слайд 1"); // not «Слайд 2»
  });

  it("hides the \\begin{frame}{…} / \\end{frame} markers but keeps the body", () => {
    const sink = sinkOf(TWO_SLIDES, TWO_SLIDES.indexOf("раз"));
    const hidden = sink.atomics.map((r) => [r.from, r.to] as const);
    const begin = TWO_SLIDES.indexOf("\\begin{frame}{Актуальность}");
    const prose = TWO_SLIDES.indexOf("раз");
    // The begin head is inside a replaced range …
    expect(hidden.some(([f, t]) => f <= begin && t > begin)).toBe(true);
    // … the prose stays outside any replaced range (editable).
    expect(hidden.some(([f, t]) => f <= prose && t > prose)).toBe(false);
  });

  it("handles a plain-option frame \\begin{frame}[plain]{Title}", () => {
    const doc = "\\begin{frame}[plain]{Титул}\ntext\n\\end{frame}";
    const head = slideHeads(doc, doc.indexOf("text"))[0];
    expect(head?.title).toBe("Титул");
  });

  it("renders a block as a titled header", () => {
    const doc = "\\begin{block}{Определение}\nтело\n\\end{block}";
    const head = slideHeads(doc, doc.indexOf("тело"))[0];
    expect(head?.title).toBe("Определение");
    expect(head?.badge).toBe("Блок");
  });

  it("hides columns/column markers without a slide header", () => {
    const doc =
      "\\begin{columns}\n\\begin{column}{0.5\\textwidth}\nлево\n\\end{column}\n\\end{columns}";
    const sink = sinkOf(doc, doc.indexOf("лево"));
    const heads = sink.deco
      .map((r) => (r.value.spec as { widget?: unknown }).widget)
      .filter((w) => w instanceof SlideHeaderWidget);
    expect(heads).toHaveLength(0);
    const beginCol = doc.indexOf("\\begin{column}{0.5\\textwidth}");
    const hidden = sink.atomics.map((r) => [r.from, r.to] as const);
    expect(hidden.some(([f, t]) => f <= beginCol && t > beginCol)).toBe(true);
  });
});
