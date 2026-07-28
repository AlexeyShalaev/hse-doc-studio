import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { visualConfigFacet, type VisualConfig } from "./config";
import { buildInlineDecorations, createInlineSink } from "./inlineDecorations";
import {
  BulletWidget,
  ImagePreviewWidget,
  InputChipWidget,
  MacroFieldWidget,
  MathWidget,
  PillWidget,
  PlaceholderFieldWidget,
  SymbolWidget,
} from "./widgets";

const mkState = (
  doc: string,
  anchor = 0,
  config?: Partial<VisualConfig>,
): EditorState => {
  const state = EditorState.create({
    doc,
    selection: EditorSelection.single(anchor),
    extensions: [
      latex(),
      visualConfigFacet.of({
        macros: config?.macros ?? {},
        showComments: config?.showComments ?? false,
        hintPrefixes: config?.hintPrefixes ?? [],
        highlightEnvs: config?.highlightEnvs ?? [],
        headingAlignments: config?.headingAlignments ?? {},
        embeddedInputBasenames: config?.embeddedInputBasenames ?? [],
      }),
    ],
  });
  ensureSyntaxTree(state, doc.length, 5000);
  return state;
};

const collect = (doc: string, anchor = 0, config?: Partial<VisualConfig>) => {
  const state = mkState(doc, anchor, config);
  const sink = createInlineSink();
  buildInlineDecorations(state, 0, doc.length, sink);
  return sink;
};

const widgetsOf = (sink: ReturnType<typeof collect>) =>
  sink.deco
    .map((r) => (r.value.spec as { widget?: unknown }).widget)
    .filter((w) => w !== undefined);

const replaceRanges = (sink: ReturnType<typeof collect>) =>
  sink.atomics.map((r) => [r.from, r.to] as const);

const markClasses = (sink: ReturnType<typeof collect>) =>
  sink.deco
    .map((r) => (r.value.spec as { class?: string }).class)
    .filter((c): c is string => typeof c === "string");

describe("buildInlineDecorations — headings", () => {
  it("hides \\section{ … } braces and marks the title", () => {
    const doc = "\\section{Введение}\nТекст\n";
    // Anchor away from the command — a caret at 0 would touch and reveal it.
    const sink = collect(doc, doc.indexOf("Текст") + 1);
    expect(replaceRanges(sink)).toContainEqual([0, "\\section{".length]);
    expect(replaceRanges(sink)).toContainEqual([
      doc.indexOf("}"),
      doc.indexOf("}") + 1,
    ]);
    expect(markClasses(sink)).toContain("cm-vis-heading cm-vis-h2");
  });

  it("includes the star of \\subsection* in the hidden prefix", () => {
    const doc = "\\subsection*{Звёздочка}\n";
    const sink = collect(doc, doc.length);
    expect(replaceRanges(sink)).toContainEqual([0, "\\subsection*{".length]);
    expect(markClasses(sink)).toContain("cm-vis-heading cm-vis-h3");
  });

  it("reveals the markup when the selection touches the command", () => {
    const doc = "\\section{Введение}\n";
    const sink = collect(doc, 3); // caret inside \section
    expect(replaceRanges(sink)).toHaveLength(0);
    // Styling stays while editing (Overleaf behavior).
    expect(markClasses(sink)).toContain("cm-vis-heading cm-vis-h2");
  });

  it("applies heading alignment supplied by the real style context", () => {
    const doc = "\\section*{АННОТАЦИЯ}\nТекст\n";
    const sink = collect(doc, doc.indexOf("Текст"), {
      headingAlignments: { 2: "center" },
    });
    expect(markClasses(sink)).toContain(
      "cm-vis-heading-line cm-vis-align-center",
    );
  });
});

describe("buildInlineDecorations — inline formatting", () => {
  it("marks and hides \\textbf, composing with nested \\emph", () => {
    const doc = "a \\textbf{жирный \\emph{акцент}} b\n";
    const sink = collect(doc);
    const classes = markClasses(sink);
    expect(classes).toContain("cm-vis-b");
    expect(classes).toContain("cm-vis-i");
    expect(replaceRanges(sink)).toContainEqual([2, 2 + "\\textbf{".length]);
  });

  it("keeps the style but shows braces when the caret is inside", () => {
    const doc = "\\textbf{x}\n";
    const sink = collect(doc, 9);
    expect(replaceRanges(sink)).toHaveLength(0);
    expect(markClasses(sink)).toContain("cm-vis-b");
  });
});

describe("buildInlineDecorations — lists", () => {
  const DOC = [
    "\\begin{enumerate}",
    "\\item Один",
    "\\item Два",
    "\\begin{itemize}",
    "\\item Вложенный",
    "\\end{itemize}",
    "\\end{enumerate}",
    "",
  ].join("\n");

  it("replaces \\item with numbered bullets, restarting in nested lists", () => {
    const sink = collect(DOC);
    const bullets = sink.deco
      .map((r) => (r.value.spec as { widget?: unknown }).widget)
      .filter((w): w is BulletWidget => w instanceof BulletWidget);
    expect(bullets).toHaveLength(3);
    expect(bullets[0]?.kind).toBe("enumerate");
    expect(bullets[0]?.index).toBe(1);
    expect(bullets[1]?.index).toBe(2);
    expect(bullets[2]?.kind).toBe("itemize");
    expect(bullets[2]?.depth).toBe(1);
  });

  it("uses the optional argument as a description term", () => {
    const doc =
      "\\begin{description}\n\\item[Термин] Пояснение\n\\end{description}\n";
    const sink = collect(doc);
    const bullet = sink.deco
      .map((r) => (r.value.spec as { widget?: unknown }).widget)
      .find((w): w is BulletWidget => w instanceof BulletWidget);
    expect(bullet?.kind).toBe("description");
    expect(bullet?.label).toBe("Термин");
  });
});

describe("buildInlineDecorations — math, pills, misc", () => {
  it("widgetizes closed single-line $…$ and leaves unclosed math raw", () => {
    const closed = collect("Формула $x^2$ здесь\n");
    const widgets = closed.deco
      .map((r) => (r.value.spec as { widget?: unknown }).widget)
      .filter((w): w is MathWidget => w instanceof MathWidget);
    expect(widgets).toHaveLength(1);
    expect(widgets[0]?.tex).toBe("x^2");
    expect(widgets[0]?.display).toBe(false);

    const unclosed = collect("Формула $x^2 здесь\n");
    expect(
      unclosed.deco.some(
        (r) =>
          (r.value.spec as { widget?: unknown }).widget instanceof MathWidget,
      ),
    ).toBe(false);
  });

  it("renders \\ref/\\cite/\\label and \\includegraphics as pills", () => {
    const doc =
      "См. \\ref{fig:one} и \\cite{knuth}. \\label{sec:x}\n" +
      "\\includegraphics[width=0.5\\textwidth]{img/schema.png}\n";
    const sink = collect(doc);
    const pills = sink.deco
      .map((r) => (r.value.spec as { widget?: unknown }).widget)
      .filter((w): w is PillWidget => w instanceof PillWidget);
    expect(pills.map((p) => [p.kind, p.text])).toEqual([
      ["ref", "fig:one"],
      ["cite", "knuth"],
      ["label", "sec:x"],
      ["graphic", "schema.png"],
    ]);
  });

  it("dims comments without swallowing the newline", () => {
    const doc = "Текст\n% комментарий\nЕщё\n";
    const sink = collect(doc);
    const comment = sink.deco.find(
      (r) => (r.value.spec as { class?: string }).class === "cm-vis-comment",
    );
    expect(comment?.from).toBe(doc.indexOf("%"));
    expect(comment?.to).toBe(
      doc.indexOf("% комментарий") + "% комментарий".length,
    );
  });

  it("frames prose environments but defers tables/figures to Layer A cards", () => {
    // A prose environment (no specialized node) keeps the raw frame. `center`
    // and `quote` are NOT ones (alignment / labelled), so `minipage` stands in.
    const prose = [
      "\\begin{minipage}{\\textwidth}",
      "Текст.",
      "\\end{minipage}",
      "",
    ].join("\n");
    const frameLines = collect(prose).deco.filter(
      (r) => (r.value.spec as { class?: string }).class === "cm-vis-envframe",
    );
    expect(frameLines).toHaveLength(3);

    // A figure is a rich block card owned by Layer A — never framed here.
    const figure = [
      "\\begin{figure}[h]",
      "\\caption{Подпись}",
      "\\end{figure}",
      "",
    ].join("\n");
    expect(
      collect(figure).deco.some(
        (r) => (r.value.spec as { class?: string }).class === "cm-vis-envframe",
      ),
    ).toBe(false);
  });
});

describe("buildInlineDecorations — Word-style fields and chips", () => {
  it("renders known \\hse macros as fields with their value", () => {
    const sink = collect("Имя «\\hseProjectName» тут.\n", 0, {
      macros: { hseProjectName: "Ядро платформы" },
    });
    const field = widgetsOf(sink).find(
      (w): w is MacroFieldWidget => w instanceof MacroFieldWidget,
    );
    expect(field?.value).toBe("Ядро платформы");
    expect(field?.name).toBe("\\hseProjectName");
  });

  it("renders \\hseFill{hint} and empty-valued macros as placeholders", () => {
    const sink = collect(
      "Поле \\hseFill{укажите назначение} и \\hseEmpty здесь.\n",
      0,
      { macros: { hseEmpty: "" } },
    );
    const fills = widgetsOf(sink).filter(
      (w): w is PlaceholderFieldWidget => w instanceof PlaceholderFieldWidget,
    );
    expect(fills.map((f) => f.hint)).toEqual([
      "укажите назначение",
      "hseEmpty",
    ]);
  });

  it("renders macros whose stored value is an \\hseFill default as placeholders", () => {
    const sink = collect("Языки: \\hseLanguages.\n", 0, {
      macros: { hseLanguages: "\\hseFill{укажите языки}" },
    });
    const fill = widgetsOf(sink).find(
      (w): w is PlaceholderFieldWidget => w instanceof PlaceholderFieldWidget,
    );
    expect(fill?.hint).toBe("укажите языки");
  });

  it("leaves unknown macros and complex bodies raw", () => {
    const sink = collect("Просто \\hseUnknown и \\complex тут.\n", 0, {
      macros: { complex: "\\textbf{x}" },
    });
    expect(
      widgetsOf(sink).some(
        (w) =>
          w instanceof MacroFieldWidget || w instanceof PlaceholderFieldWidget,
      ),
    ).toBe(false);
  });

  it("replaces ~ with nbsp and \\ldots with an ellipsis", () => {
    const sink = collect("и~вот \\ldots конец.\n");
    const symbols = widgetsOf(sink).filter(
      (w): w is SymbolWidget => w instanceof SymbolWidget,
    );
    expect(symbols.map((s) => s.glyph)).toEqual([" ", "…"]);
  });

  it("renders -- and --- as display dashes in prose only", () => {
    const doc =
      "Тире~--- вот и диапазон 1--2 тут.\n" +
      "% комментарий --- с тире\n" +
      "\\includegraphics[width=0.5]{a--b.png}\n";
    const sink = collect(doc, doc.length);
    const dashes = widgetsOf(sink).filter(
      (w): w is SymbolWidget =>
        w instanceof SymbolWidget && (w.glyph === "—" || w.glyph === "–"),
    );
    expect(dashes.map((d) => d.glyph)).toEqual(["—", "–"]);
  });

  it("tints configured example environments instead of framing them", () => {
    const doc = [
      "\\begin{hseExample}",
      "Строка один",
      "Строка два",
      "\\end{hseExample}",
      "",
    ].join("\n");
    const sink = collect(doc, doc.length, { highlightEnvs: ["hseExample"] });
    const tinted = sink.deco.filter(
      (r) =>
        (r.value.spec as { class?: string }).class === "cm-vis-example-line",
    );
    expect(tinted).toHaveLength(2);
    expect(
      sink.deco.some(
        (r) => (r.value.spec as { class?: string }).class === "cm-vis-envframe",
      ),
    ).toBe(false);
  });

  it("renders an image preview when the host resolves a URL, pill otherwise", () => {
    const doc = "\\includegraphics[width=0.5]{img/schema.png}\n";
    const state = mkState(doc, doc.length);
    const withUrl = createInlineSink();
    buildInlineDecorations(state, 0, doc.length, withUrl, {
      resolveAssetUrl: (p) => `/api/files/${p}`,
    });
    const preview = withUrl.deco
      .map((r) => (r.value.spec as { widget?: unknown }).widget)
      .find((w): w is ImagePreviewWidget => w instanceof ImagePreviewWidget);
    expect(preview?.url).toBe("/api/files/img/schema.png");

    const noUrl = createInlineSink();
    buildInlineDecorations(state, 0, doc.length, noUrl, {
      resolveAssetUrl: () => null,
    });
    expect(
      noUrl.deco.some(
        (r) =>
          (r.value.spec as { widget?: unknown }).widget instanceof
          ImagePreviewWidget,
      ),
    ).toBe(false);
  });

  it("hides non-printing setup and keeps ordinary inputs as file chips", () => {
    const doc =
      "\\addcontentsline{toc}{section}{АННОТАЦИЯ}\n" +
      "\\input{requirements_table}\n" +
      "\\input{../common/title_template}\n";
    const sink = collect(doc, doc.length, {
      embeddedInputBasenames: ["title_template"],
    });
    const widgets = widgetsOf(sink);
    expect(replaceRanges(sink)).toContainEqual([
      0,
      "\\addcontentsline{toc}{section}{АННОТАЦИЯ}".length,
    ]);
    const input = widgets.find(
      (w): w is InputChipWidget => w instanceof InputChipWidget,
    );
    expect(input?.path).toBe("requirements_table");
    expect(
      widgets.some(
        (widget) =>
          widget instanceof InputChipWidget &&
          widget.path.includes("title_template"),
      ),
    ).toBe(false);
  });
});
