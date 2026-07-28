import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { visualConfigFacet } from "./config";
import { buildInlineDecorations, createInlineSink } from "./inlineDecorations";
import {
  BibFooterWidget,
  BibHeaderWidget,
  BibItemBadgeWidget,
} from "./widgets";

const BIB = String.raw`\begin{thebibliography}{99}
\bibitem{gost19101}
ГОСТ 19.101-77: Виды программ.

\bibitem{gost19102}
ГОСТ 19.102-77: Стадии разработки.
\end{thebibliography}`;

// A caret parked in neutral prose (touches no marker, begin or end).
const SAFE_ANCHOR = BIB.indexOf("Виды программ") + 2;

const mkState = (doc: string, anchor = SAFE_ANCHOR): EditorState => {
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

const collect = (doc: string, anchor = SAFE_ANCHOR) => {
  const state = mkState(doc, anchor);
  const sink = createInlineSink();
  buildInlineDecorations(state, 0, doc.length, sink);
  return sink;
};

const widgetsOf = (sink: ReturnType<typeof collect>): unknown[] =>
  sink.deco
    .map((r) => (r.value.spec as { widget?: unknown }).widget)
    .filter((w) => w !== undefined);

describe("inline bibliography", () => {
  it("renders a header, a footer and one badge per \\bibitem", () => {
    const widgets = widgetsOf(collect(BIB));
    const badges = widgets.filter(
      (w): w is BibItemBadgeWidget => w instanceof BibItemBadgeWidget,
    );
    expect(widgets.some((w) => w instanceof BibHeaderWidget)).toBe(true);
    expect(widgets.some((w) => w instanceof BibFooterWidget)).toBe(true);
    expect(badges).toHaveLength(2);
    expect(badges.map((b) => b.ordinal)).toEqual([1, 2]);
    expect(badges.map((b) => b.key)).toEqual(["gost19101", "gost19102"]);
  });

  it("hides the \\begin/\\end markup but keeps the reference text visible", () => {
    const sink = collect(BIB);
    const hidden = sink.atomics.map((r) => [r.from, r.to] as const);
    const begin = BIB.indexOf("\\begin{thebibliography}");
    const end = BIB.indexOf("\\end{thebibliography}");
    // The begin head and the end marker fall inside a replaced (hidden) range.
    expect(hidden.some(([f, t]) => f <= begin && t > begin)).toBe(true);
    expect(hidden.some(([f, t]) => f <= end && t >= end)).toBe(true);
    // The reference prose is NOT inside any replaced range (stays editable).
    const prose = BIB.indexOf("Виды программ");
    expect(hidden.some(([f, t]) => f <= prose && t > prose)).toBe(false);
  });

  it("reveals a \\bibitem marker when the caret is inside it", () => {
    // Caret inside the first \bibitem{…} marker → that badge is not built.
    const markerPos = BIB.indexOf("gost19101");
    const badges = widgetsOf(collect(BIB, markerPos)).filter(
      (w): w is BibItemBadgeWidget => w instanceof BibItemBadgeWidget,
    );
    expect(badges.map((b) => b.key)).toEqual(["gost19102"]);
  });

  it("does not badge a \\bibitem outside a bibliography", () => {
    const widgets = widgetsOf(collect(String.raw`\bibitem{loose} text`, 18));
    expect(widgets.some((w) => w instanceof BibItemBadgeWidget)).toBe(false);
  });
});
