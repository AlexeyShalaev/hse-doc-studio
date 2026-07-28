import { describe, expect, it } from "vitest";
import { CompletionContext } from "@codemirror/autocomplete";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { slashCompletionSource, slashMenuExtension } from "./slashMenu";

const complete = (doc: string, pos: number, explicit = false) => {
  const state = EditorState.create({ doc, extensions: [latex()] });
  ensureSyntaxTree(state, doc.length, 5000);
  return slashCompletionSource(new CompletionContext(state, pos, explicit));
};

describe("slashCompletionSource", () => {
  it("opens at line start and filters from after the slash", () => {
    const result = complete("/", 1);
    expect(result).not.toBeNull();
    expect(result?.from).toBe(1); // filter text excludes the slash
    expect(result?.options.map((o) => o.label)).toContain("Раздел");
    expect(result?.options.map((o) => o.label)).toContain("Таблица");
  });

  it("opens after whitespace mid-line", () => {
    const doc = "Текст /рис";
    const result = complete(doc, doc.length);
    expect(result).not.toBeNull();
    expect(result?.from).toBe(doc.indexOf("/") + 1);
  });

  it("stays closed inside paths and dates", () => {
    const doc = "см. img/schema";
    expect(complete(doc, doc.length)).toBeNull();
    const date = "01/09";
    expect(complete(date, date.length)).toBeNull();
  });

  it("stays closed without a slash", () => {
    expect(complete("Просто текст", 6)).toBeNull();
  });

  it("registers through latexLanguage.data so the autocomplete UI finds it", () => {
    const state = EditorState.create({
      doc: "/",
      extensions: [latex(), slashMenuExtension],
    });
    expect(state.languageDataAt("autocomplete", 1)).toContain(
      slashCompletionSource,
    );
  });
});
