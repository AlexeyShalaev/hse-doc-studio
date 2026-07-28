import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { computeOutline, outlineActiveIndex } from "./outline";

const mkState = (doc: string): EditorState => {
  const state = EditorState.create({ doc, extensions: [latex()] });
  ensureSyntaxTree(state, doc.length, 5000);
  return state;
};

const DOC = [
  "\\chapter{Введение}",
  "Текст.",
  "\\section{Обзор \\textbf{области}}",
  "Ещё текст.",
  "\\subsection*{Метод \\hseFill{укажите метод}}",
  "Конец.",
  "",
].join("\n");

describe("computeOutline", () => {
  it("collects headings with levels, lines and cleaned titles", () => {
    const items = computeOutline(mkState(DOC));
    expect(items.map((i) => [i.level, i.title, i.line])).toEqual([
      [1, "Введение", 1],
      [2, "Обзор области", 3],
      [3, "Метод ⟨укажите метод⟩", 5],
    ]);
  });

  it("memoizes per tree identity", () => {
    const state = mkState(DOC);
    expect(computeOutline(state)).toBe(computeOutline(state));
  });

  it("returns an empty outline for documents without headings", () => {
    expect(computeOutline(mkState("Просто текст\n"))).toEqual([]);
  });
});

describe("outlineActiveIndex", () => {
  it("maps the caret to the containing section", () => {
    const state = mkState(DOC);
    const items = computeOutline(state);
    expect(outlineActiveIndex(items, 0)).toBe(0);
    expect(outlineActiveIndex(items, DOC.indexOf("Ещё"))).toBe(1);
    expect(outlineActiveIndex(items, DOC.indexOf("Конец"))).toBe(2);
  });

  it("returns -1 before the first heading", () => {
    const doc = "Преамбула-текст\n\\section{X}\n";
    const state = mkState(doc);
    const items = computeOutline(state);
    expect(outlineActiveIndex(items, 2)).toBe(-1);
  });
});
