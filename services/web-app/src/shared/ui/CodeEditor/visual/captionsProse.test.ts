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

const classesOf = (doc: string, anchor: number): string[] =>
  sinkOf(doc, anchor)
    .deco.map((r) => (r.value.spec as { class?: string }).class)
    .filter((c): c is string => typeof c === "string");

describe("\\captionof", () => {
  it("marks the caption text and hides the \\captionof{type} wrapper", () => {
    const doc = "x\n\\captionof{table}{Подпись таблицы}\ny";
    const sink = sinkOf(doc, 0);
    const classes = sink.deco
      .map((r) => (r.value.spec as { class?: string }).class)
      .filter((c): c is string => typeof c === "string");
    expect(classes).toContain("cm-vis-caption");
    const wrapper = doc.indexOf("\\captionof{table}");
    const hidden = sink.atomics.map((r) => [r.from, r.to] as const);
    expect(hidden.some(([f, t]) => f <= wrapper && t > wrapper)).toBe(true);
  });
});

describe("named prose environments", () => {
  const heads = (doc: string, anchor: number): SlideHeaderWidget[] =>
    sinkOf(doc, anchor)
      .deco.map((r) => (r.value.spec as { widget?: unknown }).widget)
      .filter((w): w is SlideHeaderWidget => w instanceof SlideHeaderWidget);

  it("labels \\begin{abstract} «Аннотация» and keeps the body editable", () => {
    const doc = "\\begin{abstract}\nтекст аннотации\n\\end{abstract}";
    const at = doc.indexOf("текст");
    expect(heads(doc, at)[0]?.title).toBe("Аннотация");
    const hidden = sinkOf(doc, at).atomics.map((r) => [r.from, r.to] as const);
    expect(hidden.some(([f, t]) => f <= at && t > at)).toBe(false);
  });

  it("labels \\begin{IEEEkeywords} «Ключевые слова»", () => {
    const doc = "\\begin{IEEEkeywords}\nsoftware, latex\n\\end{IEEEkeywords}";
    expect(heads(doc, doc.indexOf("software"))[0]?.title).toBe(
      "Ключевые слова",
    );
  });
});

describe("\\centering", () => {
  it("centers the rest of its brace group", () => {
    const doc = "{\\centering\nпо центру\n}";
    expect(classesOf(doc, doc.indexOf("центру"))).toContain(
      "cm-vis-align-center",
    );
  });

  it("does not center at document top level (no enclosing group)", () => {
    const doc = "\\centering\nобычный текст";
    expect(classesOf(doc, doc.indexOf("обычный"))).not.toContain(
      "cm-vis-align-center",
    );
  });
});
