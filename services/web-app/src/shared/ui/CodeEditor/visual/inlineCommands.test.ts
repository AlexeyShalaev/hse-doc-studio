import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { visualConfigFacet } from "./config";
import { buildInlineDecorations, createInlineSink } from "./inlineDecorations";
import { LineBreakWidget, PillWidget } from "./widgets";

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

const widgetsOf = (doc: string, anchor = 0): unknown[] => {
  const sink = createInlineSink();
  buildInlineDecorations(mkState(doc, anchor), 0, doc.length, sink);
  return sink.deco
    .map((r) => (r.value.spec as { widget?: unknown }).widget)
    .filter((w) => w !== undefined);
};

const pill = (doc: string): PillWidget | undefined =>
  widgetsOf(`ok. ${doc}`, 1).find(
    (w): w is PillWidget => w instanceof PillWidget,
  );

describe("inline commands → pills / markers", () => {
  it("\\url → link pill with the URL", () => {
    const p = pill("\\url{https://hse.ru/a}");
    expect(p?.kind).toBe("link");
    expect(p?.text).toBe("https://hse.ru/a");
  });

  it("\\href → link pill with the label", () => {
    const p = pill("\\href{https://hse.ru}{сайт}");
    expect(p?.kind).toBe("link");
    expect(p?.text).toBe("сайт");
  });

  it("\\href → renders a formatted label as its text, not raw markup", () => {
    const p = pill("\\href{https://hse.ru}{\\textbf{сайт}}");
    expect(p?.kind).toBe("link");
    expect(p?.text).toBe("сайт");
  });

  it("\\footnote → note marker carrying the note text", () => {
    const p = pill("текст\\footnote{это сноска}");
    expect(p?.kind).toBe("note");
    expect(p?.text).toBe("это сноска");
  });

  it("\\todo → amber todo pill", () => {
    const p = pill("\\todo{дописать вывод}");
    expect(p?.kind).toBe("todo");
    expect(p?.text).toBe("дописать вывод");
  });

  it("\\reqref → requirement pill", () => {
    const p = pill("см. \\reqref{ТЗ-01}");
    expect(p?.kind).toBe("req");
    expect(p?.text).toBe("ТЗ-01");
  });

  it("\\pageref is already a ref pill (Ref node)", () => {
    const p = pill("с. \\pageref{LastPage}");
    expect(p?.kind).toBe("ref");
    expect(p?.text).toBe("LastPage");
  });

  it("\\newline → a line-break glyph widget", () => {
    const widgets = widgetsOf("строка\\newline ещё", 1);
    expect(widgets.some((w) => w instanceof LineBreakWidget)).toBe(true);
  });

  it("a declaration chip (\\itshape) hides only the token, not following text", () => {
    // `\itshape [Схема]` — the grammar attaches `[Схема]` as an optional arg;
    // it must stay visible (only `\itshape` is hidden).
    const doc = "ok \\itshape [Схема] далее";
    const sink = createInlineSink();
    buildInlineDecorations(mkState(doc, 0), 0, doc.length, sink);
    const hidden = sink.atomics.map((r) => [r.from, r.to] as const);
    const schema = doc.indexOf("Схема");
    expect(hidden.some(([f, t]) => f <= schema && t > schema)).toBe(false);
    const token = doc.indexOf("\\itshape");
    expect(hidden.some(([f, t]) => f <= token && t > token)).toBe(true);
  });

  it("reveals the raw command when the caret is inside it", () => {
    const doc = "ok. \\todo{x}";
    const at = doc.indexOf("todo");
    const p = widgetsOf(doc, at).find((w) => w instanceof PillWidget);
    expect(p).toBeUndefined();
  });
});

const stylesOf = (doc: string, anchor = 0): string[] => {
  const sink = createInlineSink();
  buildInlineDecorations(mkState(doc, anchor), 0, doc.length, sink);
  return sink.deco
    .map(
      (r) =>
        (r.value.spec as { attributes?: { style?: string } }).attributes?.style,
    )
    .filter((s): s is string => typeof s === "string");
};

describe("\\textcolor", () => {
  it("renders the body in the resolved color and hides the wrapper", () => {
    const styles = stylesOf("ok \\textcolor{hseblue}{Цель} тут", 1);
    expect(styles.some((s) => s.includes("color:#102D69"))).toBe(true);
  });

  it("falls back to plain text for an unknown color (no style mark)", () => {
    const styles = stylesOf("ok \\textcolor{blue!15}{X} тут", 1);
    expect(styles.some((s) => s.startsWith("color:"))).toBe(false);
  });
});
