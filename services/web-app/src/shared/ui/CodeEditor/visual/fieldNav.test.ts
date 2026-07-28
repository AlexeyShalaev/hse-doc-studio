import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import {
  EditorSelection,
  EditorState,
  type StateCommand,
  type Transaction,
} from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { visualConfigFacet } from "./config";
import { collectFillFields, nextField, prevField } from "./fieldNav";

const DOC =
  "Начало \\hseFill{первое поле} середина.\n" +
  "Пусто: \\hseEmpty и ещё \\hseFill{второе поле}.\n";

const mkState = (anchor: number, head = anchor): EditorState => {
  const state = EditorState.create({
    doc: DOC,
    selection: EditorSelection.single(anchor, head),
    extensions: [
      latex(),
      visualConfigFacet.of({
        macros: { hseEmpty: "" },
        showComments: false,
        hintPrefixes: [],
        highlightEnvs: [],
      }),
    ],
  });
  ensureSyntaxTree(state, DOC.length, 5000);
  return state;
};

const run = (command: StateCommand, state: EditorState): EditorState => {
  let out = state;
  command({
    state,
    dispatch: (tr: Transaction) => {
      out = tr.state;
    },
  });
  return out;
};

describe("collectFillFields", () => {
  it("finds \\hseFill commands (whole) and empty macros (name only)", () => {
    const fields = collectFillFields(mkState(0));
    expect(fields).toHaveLength(3);
    const texts = fields.map((f) => DOC.slice(f.from, f.to));
    expect(texts[0]).toBe("\\hseFill{первое поле}");
    expect(texts[1]).toBe("\\hseEmpty");
    expect(texts[2]).toBe("\\hseFill{второе поле}");
  });
});

describe("nextField / prevField", () => {
  it("selects the next field after the caret and wraps around", () => {
    const first = run(nextField, mkState(0));
    expect(first.selection.main.from).toBe(DOC.indexOf("\\hseFill{первое"));
    const afterLast = run(nextField, mkState(DOC.indexOf("второе") + 6));
    expect(afterLast.selection.main.from).toBe(DOC.indexOf("\\hseFill{первое"));
  });

  it("advances from a selected field to the following one", () => {
    const firstFrom = DOC.indexOf("\\hseFill{первое");
    const firstTo = firstFrom + "\\hseFill{первое поле}".length;
    const out = run(nextField, mkState(firstFrom, firstTo));
    expect(out.selection.main.from).toBe(DOC.indexOf("\\hseEmpty"));
  });

  it("selects the previous field and wraps backwards", () => {
    const out = run(prevField, mkState(DOC.indexOf("середина")));
    expect(out.selection.main.from).toBe(DOC.indexOf("\\hseFill{первое"));
    const wrapped = run(prevField, mkState(0));
    expect(wrapped.selection.main.from).toBe(DOC.indexOf("\\hseFill{второе"));
  });

  it("falls through when the document has no fields", () => {
    const state = EditorState.create({
      doc: "просто текст",
      extensions: [latex()],
    });
    ensureSyntaxTree(state, state.doc.length, 5000);
    let dispatched = false;
    const handled = nextField({
      state,
      dispatch: () => {
        dispatched = true;
      },
    });
    expect(handled).toBe(false);
    expect(dispatched).toBe(false);
  });
});
