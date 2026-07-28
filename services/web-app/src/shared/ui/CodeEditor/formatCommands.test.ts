import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import {
  EditorSelection,
  EditorState,
  type StateCommand,
  type Transaction,
} from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { editorCommands, selectionFormatState } from "./formatCommands";

const mkState = (doc: string, anchor: number, head?: number): EditorState => {
  const state = EditorState.create({
    doc,
    selection: EditorSelection.single(anchor, head ?? anchor),
    extensions: [latex()],
  });
  ensureSyntaxTree(state, doc.length, 5000);
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

describe("bold / italic toggles", () => {
  it("wraps a selection in \\textbf{…}", () => {
    const out = run(editorCommands.bold, mkState("привет", 0, 6));
    expect(out.doc.toString()).toBe("\\textbf{привет}");
    expect(out.sliceDoc(out.selection.main.from, out.selection.main.to)).toBe(
      "привет",
    );
  });

  it("unwraps when the caret already sits inside \\textbf{…}", () => {
    const out = run(editorCommands.bold, mkState("\\textbf{привет}", 10));
    expect(out.doc.toString()).toBe("привет");
  });

  it("italic inserts \\textit but also unwraps \\emph", () => {
    expect(run(editorCommands.italic, mkState("x", 0, 1)).doc.toString()).toBe(
      "\\textit{x}",
    );
    expect(
      run(editorCommands.italic, mkState("\\emph{акцент}", 8)).doc.toString(),
    ).toBe("акцент");
  });
});

describe("heading level", () => {
  it("swaps \\section for \\subsection keeping the star and title", () => {
    const out = run(
      editorCommands["heading:subsection"],
      mkState("\\section*{Название}", 12),
    );
    expect(out.doc.toString()).toBe("\\subsection*{Название}");
  });

  it("unwraps a heading to plain text", () => {
    const out = run(
      editorCommands["heading:none"],
      mkState("\\section{Название}", 12),
    );
    expect(out.doc.toString()).toBe("Название");
  });

  it("wraps a plain line into a heading", () => {
    const out = run(
      editorCommands["heading:section"],
      mkState("Просто строка", 4),
    );
    expect(out.doc.toString()).toBe("\\section{Просто строка}");
  });
});

describe("list toggles", () => {
  it("wraps selected lines into itemize", () => {
    const out = run(editorCommands.bulletList, mkState("один\nдва", 0, 8));
    expect(out.doc.toString()).toBe(
      "\\begin{itemize}\n\\item один\n\\item два\n\\end{itemize}",
    );
  });

  it("renames itemize → enumerate from inside", () => {
    const doc = "\\begin{itemize}\n\\item один\n\\end{itemize}";
    const out = run(
      editorCommands.numberedList,
      mkState(doc, doc.indexOf("один")),
    );
    expect(out.doc.toString()).toBe(
      "\\begin{enumerate}\n\\item один\n\\end{enumerate}",
    );
  });

  it("unwraps the current list back to plain lines", () => {
    const doc = "\\begin{itemize}\n\\item один\n\\item два\n\\end{itemize}";
    const out = run(
      editorCommands.bulletList,
      mkState(doc, doc.indexOf("один")),
    );
    expect(out.doc.toString()).toBe("один\nдва");
  });
});

describe("selectionFormatState", () => {
  it("reports the markup enclosing the caret", () => {
    const doc = "\\section{Заголовок}\n\\textbf{жирный}\n";
    const inTitle = selectionFormatState(mkState(doc, doc.indexOf("Загол")));
    expect(inTitle.heading).toBe("section");
    expect(inTitle.bold).toBe(false);
    const inBold = selectionFormatState(
      mkState(doc, doc.indexOf("жирный") + 2),
    );
    expect(inBold.bold).toBe(true);
    expect(inBold.heading).toBe(null);
  });

  it("reports the enclosing list kind", () => {
    const doc = "\\begin{enumerate}\n\\item один\n\\end{enumerate}\n";
    const state = selectionFormatState(mkState(doc, doc.indexOf("один")));
    expect(state.list).toBe("enumerate");
  });
});

describe("math templates", () => {
  it("wraps the selection into $…$ / \\[…\\]", () => {
    expect(
      run(editorCommands.inlineMath, mkState("x", 0, 1)).doc.toString(),
    ).toBe("$x$");
    expect(
      run(editorCommands.displayMath, mkState("x", 0, 1)).doc.toString(),
    ).toBe("\\[\nx\n\\]");
  });
});

describe("visual insert templates", () => {
  it("inserts a guided figure and selects its first field", () => {
    const out = run(editorCommands["insert:figure"], mkState("", 0));
    expect(out.doc.toString()).toContain("\\begin{figure}[htbp]");
    expect(out.doc.toString()).toContain("\\includegraphics");
    expect(out.sliceDoc(out.selection.main.from, out.selection.main.to)).toBe(
      "путь к изображению",
    );
  });

  it("wraps selected prose in a footnote without losing the selection", () => {
    const out = run(editorCommands["insert:footnote"], mkState("важно", 0, 5));
    expect(out.doc.toString()).toBe("\\footnote{важно}");
    expect(out.sliceDoc(out.selection.main.from, out.selection.main.to)).toBe(
      "важно",
    );
  });

  it("puts a block quote on separate lines inside prose", () => {
    const out = run(
      editorCommands["insert:quote"],
      mkState("до цитата после", 3, 9),
    );
    expect(out.doc.toString()).toContain(
      "\n\\begin{quote}\nцитата\n\\end{quote}\n",
    );
  });

  it("inserts academic citation and table templates with guided fields", () => {
    const citation = run(editorCommands["insert:citation"], mkState("", 0));
    expect(citation.doc.toString()).toBe("\\cite{\\hseFill{ключ источника}}");
    const table = run(editorCommands["insert:table"], mkState("", 0));
    expect(table.doc.toString()).toContain("\\begin{tabular}{|l|l|}");
    expect(table.doc.toString()).toContain("\\caption{\\hseFill{");
  });
});
