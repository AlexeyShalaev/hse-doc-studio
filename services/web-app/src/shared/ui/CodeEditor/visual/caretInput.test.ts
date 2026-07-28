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
import { atomicBlocksField, preambleCollapsedField } from "./atomicBlocks";
import { setPreambleCollapsed } from "./effects";
import {
  endTargetFor,
  guardBackspaceAfterHiddenBlock,
  guardDeleteBeforeHiddenBlock,
  homeTargetFor,
  insertParagraphAfterHeading,
} from "./caretInput";

const mkState = (doc: string, anchor: number): EditorState => {
  const state = EditorState.create({
    doc,
    selection: EditorSelection.single(anchor),
    extensions: [
      latex(),
      visualConfigFacet.of({
        macros: {},
        showComments: false,
        hintPrefixes: ["Подсказка:"],
        highlightEnvs: ["hseExample"],
      }),
      preambleCollapsedField,
      atomicBlocksField,
    ],
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

describe("insertParagraphAfterHeading (Enter in a heading)", () => {
  it("opens a new paragraph below instead of splitting the argument", () => {
    const doc = "\\section{АННОТАЦИЯ}\nТекст\n";
    const pos = doc.indexOf("АННОТ") + 5; // caret mid-title
    const { handled, state } = run(
      insertParagraphAfterHeading,
      mkState(doc, pos),
    );
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe("\\section{АННОТАЦИЯ}\n\nТекст\n");
    expect(state.selection.main.head).toBe("\\section{АННОТАЦИЯ}\n".length);
  });

  it("falls through outside headings", () => {
    const doc = "Просто текст\n";
    expect(run(insertParagraphAfterHeading, mkState(doc, 4)).handled).toBe(
      false,
    );
  });
});

describe("homeTargetFor / endTargetFor", () => {
  it("lands after hidden \\item and \\section{ prefixes", () => {
    const doc = "\\begin{itemize}\n  \\item Пункт\n\\end{itemize}\n";
    const line = doc.indexOf("  \\item");
    const state = mkState(doc, line + 9);
    expect(homeTargetFor(state, line + 9)).toBe(doc.indexOf("Пункт"));

    const headingDoc = "\\section{Заголовок}\n";
    const hState = mkState(headingDoc, 12);
    expect(homeTargetFor(hState, 12)).toBe(headingDoc.indexOf("Заголовок"));
    expect(endTargetFor(hState, 12)).toBe(headingDoc.indexOf("}"));
  });

  it("returns the plain line boundaries elsewhere", () => {
    const doc = "Обычная строка\n";
    const state = mkState(doc, 3);
    expect(homeTargetFor(state, 3)).toBe(0);
    expect(endTargetFor(state, 3)).toBe(doc.indexOf("\n"));
  });
});

describe("guardBackspaceAfterHiddenBlock", () => {
  const LIST_DOC =
    "\\begin{itemize}\n\\item один\n\\end{itemize}\nПосле списка\n";

  it("pulls the following line up into the last item (hidden \\end)", () => {
    const pos = LIST_DOC.indexOf("После");
    const { handled, state } = run(
      guardBackspaceAfterHiddenBlock,
      mkState(LIST_DOC, pos),
    );
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(
      "\\begin{itemize}\n\\item одинПосле списка\n\\end{itemize}\n",
    );
    expect(state.selection.main.head).toBe(LIST_DOC.indexOf("один") + 4);
  });

  it("reveals a hidden \\begin instead of merging into it", () => {
    const doc = "Текст\n\\begin{itemize}\n\\item один\n\\end{itemize}\n";
    const pos = doc.indexOf("\\item");
    const { handled, state } = run(
      guardBackspaceAfterHiddenBlock,
      mkState(doc, pos),
    );
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(doc); // nothing deleted
    expect(state.selection.main.head).toBe(doc.indexOf("\n\\item")); // caret inside zone → revealed
  });

  it("reveals a collapsed hint instead of merging text into the comment", () => {
    const doc =
      "\\begin{document}\n% Подсказка: заполните\nТекст\n\\end{document}\n";
    const pos = doc.indexOf("Текст");
    const { handled, state } = run(
      guardBackspaceAfterHiddenBlock,
      mkState(doc, pos),
    );
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(doc);
  });

  it("falls through after an EXPANDED preamble (nothing is hidden)", () => {
    const doc =
      "\\documentclass{a}\n\\begin{document}\nТекст\n\\end{document}\n";
    const base = mkState(doc, doc.indexOf("Текст"));
    const expanded = base.update({
      effects: setPreambleCollapsed.of(false),
    }).state;
    expect(run(guardBackspaceAfterHiddenBlock, expanded).handled).toBe(false);
    // Collapsed (default) → guard still reveals instead of merging.
    expect(run(guardBackspaceAfterHiddenBlock, base).handled).toBe(true);
  });

  it("reveals instead of merging into an EMPTY list (no item content)", () => {
    const doc = "До\n\\begin{itemize}\n\\end{itemize}\nПосле\n";
    const { handled, state } = run(
      guardBackspaceAfterHiddenBlock,
      mkState(doc, doc.indexOf("После")),
    );
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(doc); // no splice into \begin line
  });

  it("reveals (never merges) after a highlighted-env hidden \\end", () => {
    const doc = "\\begin{hseExample}\nПример\n\\end{hseExample}\nСвой текст\n";
    const { handled, state } = run(
      guardBackspaceAfterHiddenBlock,
      mkState(doc, doc.indexOf("Свой")),
    );
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(doc); // paragraph NOT pulled inside
  });

  it("falls through mid-line and at plain line starts", () => {
    expect(
      run(
        guardBackspaceAfterHiddenBlock,
        mkState(LIST_DOC, LIST_DOC.indexOf("списка")),
      ).handled,
    ).toBe(false);
    const plain = "Первая\nВторая\n";
    expect(
      run(
        guardBackspaceAfterHiddenBlock,
        mkState(plain, plain.indexOf("Вторая")),
      ).handled,
    ).toBe(false);
  });
});

describe("guardDeleteBeforeHiddenBlock", () => {
  it("reveals a collapsed hint instead of merging its first line up", () => {
    const doc =
      "\\begin{document}\nТекст\n% Подсказка: цель\nЕщё\n\\end{document}\n";
    const pos = doc.indexOf("Текст") + "Текст".length; // end of line
    const { handled, state } = run(
      guardDeleteBeforeHiddenBlock,
      mkState(doc, pos),
    );
    expect(handled).toBe(true);
    expect(state.doc.toString()).toBe(doc);
    expect(state.selection.main.head).toBe(doc.indexOf("% Подсказка"));
  });

  it("falls through before visible text and hidden list markers", () => {
    const plain = "Первая\nВторая\n";
    expect(
      run(guardDeleteBeforeHiddenBlock, mkState(plain, plain.indexOf("\n")))
        .handled,
    ).toBe(false);
    // Before a hidden \begin the caret already touch-reveals the zone.
    const list = "До\n\\begin{itemize}\n\\item а\n\\end{itemize}\n";
    expect(
      run(guardDeleteBeforeHiddenBlock, mkState(list, "До".length)).handled,
    ).toBe(false);
  });
});
