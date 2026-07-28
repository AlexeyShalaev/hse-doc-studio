import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { visualConfigFacet } from "./config";
import { buildInlineDecorations, createInlineSink } from "./inlineDecorations";
import { ManualDocItemsWidget } from "./widgets";

const MANUALS =
  "\\item «Ядро». Руководство программиста (ГОСТ~19.504-79). " +
  "\\item «Ядро». Руководство оператора (ГОСТ~19.505-79).";

const mkState = (
  doc: string,
  macros: Record<string, string>,
  anchor: number,
): EditorState => {
  const state = EditorState.create({
    doc,
    selection: EditorSelection.single(anchor),
    extensions: [
      latex(),
      visualConfigFacet.of({
        macros,
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

const widgetsOf = (
  doc: string,
  macros: Record<string, string>,
  anchor: number,
): unknown[] => {
  const state = mkState(doc, macros, anchor);
  const sink = createInlineSink();
  buildInlineDecorations(state, 0, doc.length, sink);
  return sink.deco
    .map((r) => (r.value.spec as { widget?: unknown }).widget)
    .filter((w) => w !== undefined);
};

describe("\\hseManualDocItems auto list", () => {
  const doc = "Текст.\n\\hseManualDocItems\nЕщё.";

  it("renders the manuals as a ManualDocItemsWidget, not a raw macro", () => {
    const widget = widgetsOf(doc, { hseManualDocItems: MANUALS }, 2).find(
      (w): w is ManualDocItemsWidget => w instanceof ManualDocItemsWidget,
    );
    expect(widget).toBeInstanceOf(ManualDocItemsWidget);
    expect(widget?.items).toEqual([
      "«Ядро». Руководство программиста (ГОСТ 19.504-79).",
      "«Ядро». Руководство оператора (ГОСТ 19.505-79).",
    ]);
  });

  it("reveals the raw macro when the caret is inside it", () => {
    const caretInMacro = doc.indexOf("hseManual");
    const widget = widgetsOf(doc, { hseManualDocItems: MANUALS }, caretInMacro);
    expect(widget.some((w) => w instanceof ManualDocItemsWidget)).toBe(false);
  });

  it("leaves the macro raw when no expansion is known", () => {
    const widget = widgetsOf(doc, {}, 2);
    expect(widget.some((w) => w instanceof ManualDocItemsWidget)).toBe(false);
  });

  it("drops an unresolved \\projectname to plain text", () => {
    const widget = widgetsOf(
      "x\n\\hseManualDocItems\ny",
      { hseManualDocItems: "\\item «\\projectname». Руководство оператора." },
      0,
    ).find((w): w is ManualDocItemsWidget => w instanceof ManualDocItemsWidget);
    expect(widget?.items).toEqual(["«». Руководство оператора."]);
  });

  it("resolves \\projectname and un-escapes a special-char project name", () => {
    const widget = widgetsOf(
      "x\n\\hseManualDocItems\ny",
      {
        hseManualDocItems: "\\item «\\projectname». Руководство оператора.",
        projectname: "\\hseProjectName",
        hseProjectName: "R\\&D System",
      },
      0,
    ).find((w): w is ManualDocItemsWidget => w instanceof ManualDocItemsWidget);
    expect(widget?.items).toEqual(["«R&D System». Руководство оператора."]);
  });
});
