import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import {
  EditorSelection,
  EditorState,
  type StateCommand,
  type Transaction,
} from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { insertListItem, mergeListItemBackwards } from "./listInput";

const mkState = (doc: string, anchor: number): EditorState => {
  const state = EditorState.create({
    doc,
    selection: EditorSelection.single(anchor),
    extensions: [latex()],
  });
  ensureSyntaxTree(state, doc.length, 5000);
  return state;
};

const run = (
  command: StateCommand,
  state: EditorState,
): { handled: boolean; state: EditorState } => {
  let out = state;
  const handled = command({
    state,
    dispatch: (tr: Transaction) => {
      out = tr.state;
    },
  });
  return { handled, state: out };
};

describe("insertListItem (Enter)", () => {
  it("starts a new \\item keeping the indent", () => {
    const doc = "\\begin{itemize}\n  \\item один\n\\end{itemize}";
    const pos = doc.indexOf("один") + "один".length;
    const { handled, state } = run(insertListItem, mkState(doc, pos));
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(
      "\\begin{itemize}\n  \\item один\n  \\item \n\\end{itemize}",
    );
    expect(state.selection.main.head).toBe(pos + "\n  \\item ".length);
  });

  it("on an empty item exits below the list", () => {
    const doc = "\\begin{itemize}\n\\item один\n\\item \n\\end{itemize}";
    const pos = doc.indexOf("\\item \n") + "\\item ".length;
    const { handled, state } = run(insertListItem, mkState(doc, pos));
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(
      "\\begin{itemize}\n\\item один\n\\end{itemize}\n",
    );
    expect(state.selection.main.head).toBe(state.doc.length);
  });

  it("falls through outside a list", () => {
    const { handled } = run(insertListItem, mkState("просто текст", 6));
    expect(handled).toBe(false);
  });
});

describe("mergeListItemBackwards (Backspace)", () => {
  it("merges an item into the previous one right after the prefix", () => {
    const doc = "\\begin{itemize}\n\\item один\n\\item два\n\\end{itemize}";
    const secondItemText = doc.lastIndexOf("два");
    const { handled, state } = run(
      mergeListItemBackwards,
      mkState(doc, secondItemText),
    );
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(
      "\\begin{itemize}\n\\item одиндва\n\\end{itemize}",
    );
  });

  it("refuses to merge the first item into the \\begin line", () => {
    const doc = "\\begin{itemize}\n\\item один\n\\end{itemize}";
    const { handled } = run(
      mergeListItemBackwards,
      mkState(doc, doc.indexOf("один")),
    );
    expect(handled).toBe(false);
  });

  it("falls through mid-text", () => {
    const doc = "\\begin{itemize}\n\\item один\n\\end{itemize}";
    const { handled } = run(
      mergeListItemBackwards,
      mkState(doc, doc.indexOf("один") + 2),
    );
    expect(handled).toBe(false);
  });
});
