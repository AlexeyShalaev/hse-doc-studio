import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { visualConfigFacet } from "./config";
import { buildInlineDecorations, createInlineSink } from "./inlineDecorations";

const mkState = (doc: string, anchor = 0): EditorState => {
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

const classesOf = (doc: string, anchor = 0): string[] => {
  const state = mkState(doc, anchor);
  const sink = createInlineSink();
  buildInlineDecorations(state, 0, doc.length, sink);
  return sink.deco
    .map((r) => (r.value.spec as { class?: string }).class)
    .filter((c): c is string => typeof c === "string");
};

describe("alignment environments", () => {
  it("centers \\begin{center} content instead of framing it", () => {
    const classes = classesOf(
      String.raw`\begin{center}
ГЛОССАРИЙ
\end{center}`,
    );
    expect(classes).toContain("cm-vis-align-center");
    // The raw environment frame must NOT be applied.
    expect(classes).not.toContain("cm-vis-envframe");
  });

  it("aligns flushleft and flushright content", () => {
    expect(
      classesOf(String.raw`\begin{flushright}
Справа
\end{flushright}`),
    ).toContain("cm-vis-align-right");
    expect(
      classesOf(String.raw`\begin{flushleft}
Слева
\end{flushleft}`),
    ).toContain("cm-vis-align-left");
  });

  it("still frames a genuine prose environment (minipage)", () => {
    const classes = classesOf(String.raw`\begin{minipage}{\textwidth}
Текст.
\end{minipage}`);
    expect(classes).toContain("cm-vis-envframe");
    expect(classes).not.toContain("cm-vis-align-center");
  });
});
