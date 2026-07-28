import { describe, expect, it } from "vitest";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import { latex } from "codemirror-lang-latex";
import { visualConfigFacet, type VisualConfig } from "./config";
import { externalDocumentSync } from "./effects";
import {
  atomicBlocksField,
  computeBlockZones,
  materializeBlockZones,
  preambleCollapsedField,
  protectEmbeddedInputs,
  type BlockZone,
} from "./atomicBlocks";
import {
  ChangeLogInputBlockWidget,
  EmbeddedInputBlockWidget,
  EnvironmentBlockWidget,
  FigureBlockWidget,
  RequirementsTableInputBlockWidget,
  TableBlockWidget,
  TitleInputBlockWidget,
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
        embeddedInputKinds: config?.embeddedInputKinds ?? {},
        embeddedInputSources: config?.embeddedInputSources ?? {},
      }),
    ],
  });
  ensureSyntaxTree(state, doc.length, 5000);
  return state;
};

const DOC = [
  "\\documentclass{extreport}",
  "\\usepackage{amsmath}",
  "\\begin{document}",
  "Текст",
  "\\[ E = mc^2 \\]",
  "$$ a = b $$",
  "\\begin{equation}",
  "F = ma",
  "\\end{equation}",
  "\\begin{itemize}",
  "\\item Один",
  "\\end{itemize}",
  "\\end{document}",
  "",
].join("\n");

describe("computeBlockZones", () => {
  it("collapses the preamble up to the \\begin{document} line", () => {
    const zones = computeBlockZones(mkState(DOC));
    const preamble = zones.find((z) => z.kind === "preamble");
    expect(preamble).toBeDefined();
    expect(preamble?.from).toBe(0);
    expect(preamble?.to).toBe(
      DOC.indexOf("\\begin{document}") + "\\begin{document}".length,
    );
    expect(preamble && "lineCount" in preamble && preamble.lineCount).toBe(3);
  });

  it("skips the preamble for fragment files without \\begin{document}", () => {
    const zones = computeBlockZones(mkState("Просто $x$ текст\n"));
    expect(zones.some((z) => z.kind === "preamble")).toBe(false);
  });

  it("finds display math (\\[..\\], $$..$$, equation) as full-line blocks", () => {
    const zones = computeBlockZones(mkState(DOC)).filter(
      (z): z is Extract<BlockZone, { kind: "math" }> => z.kind === "math",
    );
    expect(zones).toHaveLength(3);
    expect(zones.every((z) => z.block)).toBe(true);
    expect(zones[0]?.tex).toBe(" E = mc^2 ");
    expect(zones[1]?.tex).toBe(" a = b ");
    // Equation environments go to KaTeX whole (it renders them natively).
    expect(zones[2]?.tex).toContain("\\begin{equation}");
  });

  it("ignores unterminated display math", () => {
    const zones = computeBlockZones(mkState("$$ a = b\n"));
    expect(zones.some((z) => z.kind === "math")).toBe(false);
  });

  it("hides lines holding only a list \\begin/\\end marker", () => {
    const zones = computeBlockZones(mkState(DOC)).filter(
      (z) => z.kind === "hiddenLine",
    );
    expect(zones).toHaveLength(2);
    const beginAt = DOC.indexOf("\\begin{itemize}");
    // The preceding newline is swallowed so no blank line remains.
    expect(zones[0]?.from).toBe(beginAt - 1);
    expect(zones[0]?.to).toBe(beginAt + "\\begin{itemize}".length);
  });

  it("keeps a marker sharing its line with other content visible", () => {
    const doc = "\\begin{itemize} % пояснение\n\\item a\n\\end{itemize}\n";
    const zones = computeBlockZones(mkState(doc)).filter(
      (z) => z.kind === "hiddenLine",
    );
    expect(zones).toHaveLength(1); // only the \end line qualifies
  });

  it("collapses runs of full-line comments (outside the preamble)", () => {
    const doc = [
      "\\documentclass{article}",
      "% преамбульный комментарий",
      "\\begin{document}",
      "Текст",
      "% =====",
      "% АННОТАЦИЯ",
      "Дальше % хвостовой",
      "\\end{document}",
      "",
    ].join("\n");
    const zones = computeBlockZones(mkState(doc)).filter(
      (z): z is Extract<BlockZone, { kind: "comments" }> =>
        z.kind === "comments",
    );
    expect(zones).toHaveLength(1); // preamble comment excluded, trailing kept
    expect(zones[0]?.count).toBe(2);
    expect(zones[0]?.from).toBe(doc.indexOf("% ====="));

    const visible = computeBlockZones(mkState(doc, 0, { showComments: true }));
    expect(visible.some((z) => z.kind === "comments")).toBe(false);
  });

  it("classifies «Подсказка:» runs as hint zones with joined stripped text", () => {
    const doc = [
      "\\begin{document}",
      "% Подсказка: перечислите основные функции,",
      "% которые выполняет программа.",
      "Текст",
      "% просто комментарий",
      "\\end{document}",
      "",
    ].join("\n");
    const zones = computeBlockZones(
      mkState(doc, 0, { hintPrefixes: ["Подсказка:"] }),
    );
    const hints = zones.filter(
      (z): z is Extract<BlockZone, { kind: "hint" }> => z.kind === "hint",
    );
    expect(hints).toHaveLength(1);
    expect(hints[0]?.count).toBe(2);
    expect(hints[0]?.text).toBe(
      "перечислите основные функции, которые выполняет программа.",
    );
    expect(zones.filter((z) => z.kind === "comments")).toHaveLength(1);
  });

  it("turns configured environments into a banner + hidden end line", () => {
    const doc = [
      "\\begin{hseExample}",
      "Текст образца",
      "\\end{hseExample}",
      "",
    ].join("\n");
    const zones = computeBlockZones(
      mkState(doc, 0, { highlightEnvs: ["hseExample"] }),
    );
    const banner = zones.find((z) => z.kind === "banner");
    expect(banner?.from).toBe(0);
    expect(banner?.to).toBe("\\begin{hseExample}".length);
    const hidden = zones.filter(
      (z): z is Extract<BlockZone, { kind: "hiddenLine" }> =>
        z.kind === "hiddenLine",
    );
    expect(hidden).toHaveLength(1);
    // "envEnd", not "end" — the Backspace guard must reveal, never merge
    // a student's paragraph into the sample block.
    expect(hidden[0]?.marker).toBe("envEnd");
    // Unconfigured runs keep the raw frame path (no zones at all).
    const unconfigured = computeBlockZones(mkState(doc, 0));
    expect(unconfigured.some((z) => z.kind === "banner")).toBe(false);
  });

  it("classifies only configured full-line inputs as protected blocks", () => {
    const doc = [
      "\\input{../common/title_template}",
      "\\input{requirements_table}",
      "Текст \\input{title_template} внутри строки",
      "",
    ].join("\n");
    const zones = computeBlockZones(
      mkState(doc, doc.length, {
        embeddedInputBasenames: ["title_template.tex"],
      }),
    ).filter(
      (zone): zone is Extract<BlockZone, { kind: "embeddedInput" }> =>
        zone.kind === "embeddedInput",
    );
    expect(zones).toHaveLength(1);
    expect(zones[0]?.path).toBe("../common/title_template");
    expect(zones[0]?.from).toBe(0);
    expect(zones[0]?.to).toBe("\\input{../common/title_template}".length);
  });

  it("supports a literal bare input target", () => {
    const doc = "\\input requirements_table.tex\n";
    const zones = computeBlockZones(
      mkState(doc, doc.length, {
        embeddedInputBasenames: ["requirements_table"],
        embeddedInputKinds: {
          "requirements_table.tex": "requirementsTable",
        },
      }),
    ).filter(
      (zone): zone is Extract<BlockZone, { kind: "embeddedInput" }> =>
        zone.kind === "embeddedInput",
    );
    expect(zones).toMatchObject([
      {
        path: "requirements_table.tex",
        variant: "requirementsTable",
      },
    ]);
  });

  it("renders table, figure and code environments as block cards", () => {
    const doc = [
      "\\begin{table}[H]",
      "\\centering",
      "\\caption{Стадии}",
      "\\begin{tabular}{ll}",
      "\\textbf{A} & \\textbf{B} \\\\",
      "1 & 2 \\\\",
      "\\end{tabular}",
      "\\end{table}",
      "\\begin{figure}[h]",
      "\\includegraphics{a.png}",
      "\\caption{Рис}",
      "\\end{figure}",
      "\\begin{tikzpicture}",
      "\\draw (0,0) -- (1,1);",
      "\\end{tikzpicture}",
      "",
    ].join("\n");
    const zones = computeBlockZones(mkState(doc));

    const tables = zones.filter(
      (z): z is Extract<BlockZone, { kind: "table" }> => z.kind === "table",
    );
    expect(tables).toHaveLength(1); // the inner tabular is subsumed
    expect(tables[0]?.from).toBe(doc.indexOf("\\begin{table}"));
    expect(tables[0]?.source).toContain("\\begin{tabular}");

    expect(zones.filter((z) => z.kind === "figure")).toHaveLength(1);

    const envs = zones.filter(
      (z): z is Extract<BlockZone, { kind: "environment" }> =>
        z.kind === "environment",
    );
    expect(envs).toHaveLength(1);
    expect(envs[0]?.name).toBe("tikzpicture");
  });

  it("leaves prose environments to the raw frame (no card zone)", () => {
    const doc = ["\\begin{center}", "Текст", "\\end{center}", ""].join("\n");
    const zones = computeBlockZones(mkState(doc));
    expect(
      zones.some(
        (z) =>
          z.kind === "table" || z.kind === "figure" || z.kind === "environment",
      ),
    ).toBe(false);
  });
});

describe("materializeBlockZones", () => {
  it("skips zones touched by the selection (reveal)", () => {
    const state = mkState(DOC, DOC.indexOf("E = mc^2"));
    const zones = computeBlockZones(state);
    const { deco, atomics } = materializeBlockZones(state, zones, true);
    // 1 preamble + 3 math + 2 hidden lines − 1 revealed math zone.
    expect(deco.size).toBe(zones.length - 1);
    expect(atomics.size).toBe(zones.length - 1);
  });

  it("keeps the preamble collapsed with the initial caret at position 0", () => {
    const state = mkState(DOC, 0);
    const zones = computeBlockZones(state);
    const { deco } = materializeBlockZones(state, zones, true);
    expect(deco.size).toBe(zones.length); // banner present, nothing revealed
  });

  it("expanded preamble renders a collapse chip instead of the banner", () => {
    // Anchor away from every zone — a caret at 0 would reveal the preamble.
    const state = mkState(DOC, DOC.indexOf("Текст") + 1);
    const zones = computeBlockZones(state);
    const collapsed = materializeBlockZones(state, zones, true);
    const expanded = materializeBlockZones(state, zones, false);
    expect(collapsed.atomics.size).toBe(expanded.atomics.size + 1);
    expect(expanded.deco.size).toBe(collapsed.deco.size); // chip replaces banner
  });

  it("keeps an embedded input atomic even when the caret touches it", () => {
    const doc = "\\input{../common/title_template}\n";
    const state = mkState(doc, 5, {
      embeddedInputBasenames: ["title_template"],
    });
    const zones = computeBlockZones(state);
    const { deco, atomics } = materializeBlockZones(state, zones, true);
    expect(zones).toHaveLength(1);
    expect(deco.size).toBe(1);
    expect(atomics.size).toBe(1);

    let widget: unknown;
    let block = false;
    deco.between(0, doc.length, (_from, _to, value) => {
      const spec = value.spec as { widget?: unknown; block?: boolean };
      widget = spec.widget;
      block = spec.block ?? false;
    });
    expect(widget).toBeInstanceOf(EmbeddedInputBlockWidget);
    expect(block).toBe(true);
  });

  it("materializes change_log as its source-backed registration sheet", () => {
    const doc = "\\input{../common/change_log}\n";
    const source = "\\section*{ЛИСТ РЕГИСТРАЦИИ ИЗМЕНЕНИЙ}";
    const state = mkState(doc, 5, {
      macros: { doccode: "RU.01 ТЗ 01-1" },
      embeddedInputBasenames: ["change_log"],
      embeddedInputSources: { change_log: source },
    });
    const zones = computeBlockZones(state);
    expect(zones).toEqual([
      {
        kind: "embeddedInput",
        from: 0,
        to: doc.trimEnd().length,
        path: "../common/change_log",
        variant: "changeLog",
        source,
      },
    ]);

    let widget: unknown;
    materializeBlockZones(state, zones, true).deco.between(
      0,
      doc.length,
      (_from, _to, value) => {
        widget = (value.spec as { widget?: unknown }).widget;
      },
    );
    expect(widget).toBeInstanceOf(ChangeLogInputBlockWidget);
  });

  it("materializes distinct ESPD title and requirements renderers", () => {
    const doc = [
      "\\input{../common/title_template}",
      "\\input{requirements_table}",
      "",
    ].join("\n");
    const state = mkState(doc, doc.length, {
      macros: { projectname: "Проект", docname: "Техническое задание" },
      embeddedInputBasenames: ["title_template", "requirements_table"],
      embeddedInputKinds: {
        "../common/title_template": "titlePages",
        requirements_table: "requirementsTable",
      },
      embeddedInputSources: {
        "../common/title_template": "ЛИСТ УТВЕРЖДЕНИЯ",
        requirements_table: "\\begin{longtable}{llll}\\end{longtable}",
      },
    });
    const widgets: unknown[] = [];
    materializeBlockZones(state, computeBlockZones(state), true).deco.between(
      0,
      doc.length,
      (_from, _to, value) => {
        widgets.push((value.spec as { widget?: unknown }).widget);
      },
    );
    expect(widgets).toHaveLength(2);
    expect(widgets[0]).toBeInstanceOf(TitleInputBlockWidget);
    expect(widgets[1]).toBeInstanceOf(RequirementsTableInputBlockWidget);
  });

  it("blocks edits to the embedded command while allowing nearby text", () => {
    const doc = "\\input{../common/title_template}\n";
    const state = EditorState.create({
      doc,
      extensions: [
        latex(),
        visualConfigFacet.of({
          macros: {},
          showComments: false,
          hintPrefixes: [],
          highlightEnvs: [],
          embeddedInputBasenames: ["title_template"],
        }),
        preambleCollapsedField,
        atomicBlocksField,
        protectEmbeddedInputs,
      ],
    });

    const removed = state.update({
      changes: { from: 0, to: doc.trimEnd().length },
    }).state;
    expect(removed.doc.toString()).toBe(doc);

    const appended = state.update({
      changes: { from: doc.length, insert: "Текст" },
    }).state;
    expect(appended.doc.toString()).toBe(doc + "Текст");
  });

  it("protects command boundaries and adjacent line breaks", () => {
    const doc = "До\n\\input{requirements_table}\nПосле\n";
    const state = EditorState.create({
      doc,
      extensions: [
        latex(),
        visualConfigFacet.of({
          macros: {},
          showComments: false,
          hintPrefixes: [],
          highlightEnvs: [],
          embeddedInputBasenames: ["requirements_table"],
          embeddedInputKinds: { requirements_table: "requirementsTable" },
        }),
        preambleCollapsedField,
        atomicBlocksField,
        protectEmbeddedInputs,
      ],
    });
    const from = doc.indexOf("\\input");
    const to = from + "\\input{requirements_table}".length;

    expect(
      state
        .update({ changes: { from, insert: "inline " } })
        .state.doc.toString(),
    ).toBe(doc);
    expect(
      state
        .update({ changes: { from: to, insert: " inline" } })
        .state.doc.toString(),
    ).toBe(doc);
    expect(
      state
        .update({ changes: { from: from - 1, to: from } })
        .state.doc.toString(),
    ).toBe(doc);
    expect(
      state.update({ changes: { from: to, to: to + 1 } }).state.doc.toString(),
    ).toBe(doc);
  });

  it("allows a trusted controlled-value replacement", () => {
    const doc = "\\input{../common/title_template}\n";
    const state = EditorState.create({
      doc,
      extensions: [
        latex(),
        visualConfigFacet.of({
          macros: {},
          showComments: false,
          hintPrefixes: [],
          highlightEnvs: [],
          embeddedInputBasenames: ["title_template"],
          embeddedInputKinds: { title_template: "titlePages" },
        }),
        preambleCollapsedField,
        atomicBlocksField,
        protectEmbeddedInputs,
      ],
    });
    const replacement = "Откат из React\n";
    const next = state.update({
      changes: { from: 0, to: doc.length, insert: replacement },
      annotations: externalDocumentSync.of(true),
    }).state;
    expect(next.doc.toString()).toBe(replacement);
  });

  it("materializes distinct table / figure / environment card widgets", () => {
    const doc = [
      "\\begin{table}[H]",
      "\\begin{tabular}{ll}A & B \\\\ \\end{tabular}",
      "\\end{table}",
      "\\begin{figure}",
      "\\includegraphics{a.png}",
      "\\end{figure}",
      "\\begin{tikzpicture}",
      "\\draw (0,0);",
      "\\end{tikzpicture}",
      "",
    ].join("\n");
    const state = mkState(doc, doc.length);
    const widgets: unknown[] = [];
    materializeBlockZones(state, computeBlockZones(state), true).deco.between(
      0,
      doc.length,
      (_from, _to, value) => {
        widgets.push((value.spec as { widget?: unknown }).widget);
      },
    );
    expect(widgets.some((w) => w instanceof TableBlockWidget)).toBe(true);
    expect(widgets.some((w) => w instanceof FigureBlockWidget)).toBe(true);
    expect(widgets.some((w) => w instanceof EnvironmentBlockWidget)).toBe(true);
  });

  it("skips a table card when the selection reveals it", () => {
    const doc = [
      "\\begin{table}[H]",
      "\\begin{tabular}{ll}A & B \\\\ \\end{tabular}",
      "\\end{table}",
      "",
    ].join("\n");
    const state = mkState(doc, doc.indexOf("A & B"));
    const zones = computeBlockZones(state);
    expect(zones.some((z) => z.kind === "table")).toBe(true);
    let hasTable = false;
    materializeBlockZones(state, zones, true).deco.between(
      0,
      doc.length,
      (_from, _to, value) => {
        if (
          (value.spec as { widget?: unknown }).widget instanceof
          TableBlockWidget
        ) {
          hasTable = true;
        }
      },
    );
    expect(hasTable).toBe(false);
  });
});
