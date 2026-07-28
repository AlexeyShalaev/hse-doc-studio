import {
  snippet,
  type Completion,
  type CompletionContext,
  type CompletionResult,
} from "@codemirror/autocomplete";
import { latexLanguage } from "codemirror-lang-latex";
import type { Extension } from "@codemirror/state";
import type { EditorView } from "@codemirror/view";
import { i18n } from "@shared/lib";

type ApplyFn = (
  view: EditorView,
  completion: Completion,
  from: number,
  to: number,
) => void;

/**
 * Notion-style «/» insert menu for the visual mode: type a slash at the
 * start of a line (or after a space) and pick a block in plain Russian — no
 * LaTeX knowledge needed. Templates carry `\hseFill{…}` placeholders so the
 * Tab field-navigation walks the student through what to fill in.
 *
 * Registered through `latexLanguage.data` INSIDE the visual compartment, so
 * it rides the existing autocomplete UI and vanishes in code mode.
 */

type SlashItem = {
  labelKey: string;
  detailKey?: string;
  template: string;
  type: string;
};

const ITEMS: SlashItem[] = [
  {
    labelKey: "slash.chapter",
    template: "\\chapter{${Название главы}}\n${}",
    type: "keyword",
  },
  {
    labelKey: "slash.section",
    template: "\\section{${Название раздела}}\n${}",
    type: "keyword",
  },
  {
    labelKey: "slash.subsection",
    template: "\\subsection{${Название подраздела}}\n${}",
    type: "keyword",
  },
  {
    labelKey: "slash.subsubsection",
    template: "\\subsubsection{${Название пункта}}\n${}",
    type: "keyword",
  },
  {
    labelKey: "slash.bulletList",
    template: "\\begin{itemize}\n\t\\item ${}\n\\end{itemize}",
    type: "type",
  },
  {
    labelKey: "slash.numberedList",
    template: "\\begin{enumerate}\n\t\\item ${}\n\\end{enumerate}",
    type: "type",
  },
  {
    labelKey: "slash.inlineMath",
    template: "$${x}$",
    type: "function",
  },
  {
    labelKey: "slash.displayMath",
    template: "\\[\n\t${x = y}\n\\]",
    type: "function",
  },
  {
    labelKey: "slash.figure",
    template:
      "\\begin{figure}[h]\n\t\\centering\n\t\\includegraphics[width=0.8\\textwidth]{${путь/к/файлу.png}}\n\t\\caption{\\hseFill{подпись рисунка}}\n\t\\label{fig:${метка}}\n\\end{figure}",
    type: "class",
  },
  {
    labelKey: "slash.table",
    template:
      "\\begin{table}[htbp]\n\t\\centering\n\t\\caption{\\hseFill{название таблицы}}\n\t\\label{tab:${метка}}\n\t\\begin{tabular}{|l|l|}\n\t\t\\hline\n\t\t\\hseFill{заголовок 1} & \\hseFill{заголовок 2} \\\\\n\t\t\\hline\n\t\t${} & \\hseFill{значение} \\\\\n\t\t\\hline\n\t\\end{tabular}\n\\end{table}",
    type: "class",
  },
  {
    labelKey: "slash.pageBreak",
    template: "\\newpage\n${}",
    type: "keyword",
  },
  {
    labelKey: "slash.footnote",
    template: "\\footnote{${текст сноски}}",
    type: "function",
  },
];

/** Apply the snippet AND swallow the leading `/` the user typed. */
const applyTemplate = (template: string): ApplyFn => {
  const applySnippet = snippet(template);
  return (view, completion, from, to) => {
    applySnippet(view, completion, Math.max(0, from - 1), to);
  };
};

const buildOptions = (): Completion[] =>
  ITEMS.map((item) => ({
    label: i18n.t(`sourceEdit:${item.labelKey}`),
    ...(item.detailKey
      ? { detail: i18n.t(`sourceEdit:${item.detailKey}`) }
      : {}),
    type: item.type,
    apply: applyTemplate(item.template),
  }));

export const slashCompletionSource = (
  context: CompletionContext,
): CompletionResult | null => {
  const match = context.matchBefore(/\/[\p{L}\w-]*$/u);
  if (!match) return null;
  // Only at the start of a line or after whitespace — never inside a path
  // or a date like 01/09.
  const before = context.state.doc.sliceString(
    Math.max(0, match.from - 1),
    match.from,
  );
  if (before !== "" && !/\s/.test(before)) return null;
  // `from` starts AFTER the slash so typing filters by the Russian labels;
  // applyTemplate extends the replacement one character left to eat the `/`.
  return {
    from: match.from + 1,
    options: buildOptions(),
    validFor: /^[\p{L}\w-]*$/u,
  };
};

export const slashMenuExtension: Extension = latexLanguage.data.of({
  autocomplete: slashCompletionSource,
});
