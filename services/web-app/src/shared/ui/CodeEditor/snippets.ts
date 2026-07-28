import {
  snippetCompletion,
  type Completion,
  type CompletionSource,
} from "@codemirror/autocomplete";
import { latexLanguage } from "codemirror-lang-latex";
import type { Extension } from "@codemirror/state";
import { i18n } from "@shared/lib";

// Curated multi-field snippets that augment the grammar's command/environment
// completion. `type` drives the icon; the leading "\" keeps them matchable
// against a backslash-prefixed token. Built per-completion so the localized
// `detail` labels follow a runtime language switch.
const buildSnippets = (): readonly Completion[] => [
  snippetCompletion("\\begin{${1:env}}\n\t${}\n\\end{${1:env}}", {
    label: "\\begin",
    detail: i18n.t("codeEditor:snippet.environment"),
    type: "keyword",
  }),
  snippetCompletion("\\section{${title}}", {
    label: "\\section",
    detail: i18n.t("codeEditor:snippet.section"),
    type: "keyword",
  }),
  snippetCompletion("\\subsection{${title}}", {
    label: "\\subsection",
    detail: i18n.t("codeEditor:snippet.subsection"),
    type: "keyword",
  }),
  snippetCompletion("\\subsubsection{${title}}", {
    label: "\\subsubsection",
    detail: i18n.t("codeEditor:snippet.subsubsection"),
    type: "keyword",
  }),
  snippetCompletion("\\textbf{${}}", {
    label: "\\textbf",
    detail: i18n.t("codeEditor:snippet.bold"),
    type: "function",
  }),
  snippetCompletion("\\textit{${}}", {
    label: "\\textit",
    detail: i18n.t("codeEditor:snippet.italic"),
    type: "function",
  }),
  snippetCompletion("\\emph{${}}", {
    label: "\\emph",
    detail: i18n.t("codeEditor:snippet.emphasis"),
    type: "function",
  }),
  snippetCompletion(
    "\\begin{figure}[${1:htbp}]\n\t\\centering\n\t\\includegraphics[width=${2:0.8\\textwidth}]{${3:path}}\n\t\\caption{${4:подпись}}\n\t\\label{fig:${5:key}}\n\\end{figure}",
    {
      label: "\\figure",
      detail: i18n.t("codeEditor:snippet.figure"),
      type: "keyword",
    },
  ),
  snippetCompletion(
    "\\begin{table}[${1:htbp}]\n\t\\centering\n\t\\caption{${2:подпись}}\n\t\\label{tab:${3:key}}\n\t\\begin{tabular}{${4:lcr}}\n\t\t${}\n\t\\end{tabular}\n\\end{table}",
    {
      label: "\\table",
      detail: i18n.t("codeEditor:snippet.table"),
      type: "keyword",
    },
  ),
  snippetCompletion("\\begin{itemize}\n\t\\item ${}\n\\end{itemize}", {
    label: "\\itemize",
    detail: i18n.t("codeEditor:snippet.itemize"),
    type: "keyword",
  }),
  snippetCompletion("\\begin{enumerate}\n\t\\item ${}\n\\end{enumerate}", {
    label: "\\enumerate",
    detail: i18n.t("codeEditor:snippet.enumerate"),
    type: "keyword",
  }),
  snippetCompletion("\\includegraphics[width=${1:0.8\\textwidth}]{${2:path}}", {
    label: "\\includegraphics",
    detail: i18n.t("codeEditor:snippet.includegraphics"),
    type: "function",
  }),
  snippetCompletion("\\label{${1:sec}:${2:key}}", {
    label: "\\label",
    detail: i18n.t("codeEditor:snippet.label"),
    type: "function",
  }),
  snippetCompletion("\\ref{${1:sec}:${2:key}}", {
    label: "\\ref",
    detail: i18n.t("codeEditor:snippet.ref"),
    type: "function",
  }),
  snippetCompletion("\\cite{${key}}", {
    label: "\\cite",
    detail: i18n.t("codeEditor:snippet.cite"),
    type: "function",
  }),
  snippetCompletion("\\href{${1:url}}{${2:text}}", {
    label: "\\href",
    detail: i18n.t("codeEditor:snippet.href"),
    type: "function",
  }),
  snippetCompletion("\\footnote{${}}", {
    label: "\\footnote",
    detail: i18n.t("codeEditor:snippet.footnote"),
    type: "function",
  }),
];

const latexSnippetSource: CompletionSource = (context) => {
  const token = context.matchBefore(/\\[a-zA-Z]*/);
  if (!token) return null;
  if (token.from === token.to && !context.explicit) return null;
  return {
    from: token.from,
    options: buildSnippets(),
    validFor: /^\\[a-zA-Z]*$/,
  };
};

/** Registers the snippets as an extra completion source on the LaTeX language. */
export const latexSnippetExtension: Extension = latexLanguage.data.of({
  autocomplete: latexSnippetSource,
});
