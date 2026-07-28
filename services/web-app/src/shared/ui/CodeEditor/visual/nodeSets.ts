/**
 * Node-name maps for the `codemirror-lang-latex` (Overleaf lezer-latex)
 * grammar. The visual mode walks the syntax tree by these names; they are
 * verified against the vendored parser (see visual mode tests).
 */

/** Sectioning wrapper (parent of `SectioningCommand`) → visual heading level. */
export const HEADING_LEVELS: Record<string, number> = {
  Book: 1,
  Part: 1,
  Chapter: 1,
  Section: 2,
  SubSection: 3,
  SubSubSection: 4,
  Paragraph: 5,
  SubParagraph: 5,
};

/** Inline formatting wrapper → CSS class applied to its `{…}` body. */
export const INLINE_FORMAT_CLASSES: Record<string, string> = {
  TextBoldCommand: "cm-vis-b",
  TextItalicCommand: "cm-vis-i",
  EmphasisCommand: "cm-vis-i",
  UnderlineCommand: "cm-vis-u",
  TextTeletypeCommand: "cm-vis-tt",
  TextSmallCapsCommand: "cm-vis-sc",
  TextSuperscriptCommand: "cm-vis-sup",
  TextSubscriptCommand: "cm-vis-sub",
  StrikeOutCommand: "cm-vis-strike",
};

/** Environments that render as a display-math widget (whole range replaced). */
export const MATH_BLOCK_ENVS = new Set([
  "EquationEnvironment",
  "EquationArrayEnvironment",
]);

/**
 * Environments handled by the visual mode's environment path. Structural ones
 * (see {@link cardEnvironmentKind}) collapse into rich Layer A cards; the rest
 * (generic prose environments) keep the raw source inside a subtle frame.
 */
export const FRAMED_ENVS = new Set([
  "FigureEnvironment",
  "TableEnvironment",
  "TabularEnvironment",
  "TikzPictureEnvironment",
  "VerbatimEnvironment",
  "ListingEnvironment",
  "Environment",
]);

/** Semantic renderer used for a whole environment rendered as a block card. */
export type CardEnvironmentKind = "table" | "figure" | "environment";

/** Grammar env node → card kind. These are never prose, so always cards. */
const CARD_ENV_NODE_KIND: Record<string, CardEnvironmentKind> = {
  TableEnvironment: "table",
  TabularEnvironment: "table",
  FigureEnvironment: "figure",
  TikzPictureEnvironment: "environment",
  VerbatimEnvironment: "environment",
  ListingEnvironment: "environment",
};

/**
 * Generic `Environment` names (no specialized grammar node) that still carry
 * code / drawings rather than prose, so they read better as a named card than
 * as raw source. Prose environments (quote, center, abstract…) are omitted on
 * purpose — their content must stay inline-editable.
 */
const CODE_LIKE_ENV_NAMES = new Set([
  "minted",
  "lstlisting",
  "verbatim",
  "semiverbatim",
  "Verbatim",
  "BVerbatim",
  "LVerbatim",
  "algorithm",
  "algorithmic",
  "algorithm2e",
  "algorithmicx",
  "tikzpicture",
  "circuitikz",
  "forest",
  "tikzcd",
]);

/**
 * Classify an environment node as a block card, or null when it should keep
 * the inline/framed path. Both decoration layers call this so their views of
 * "this is a card" never drift. `highlightEnvs` («образец») always wins.
 */
export const cardEnvironmentKind = (
  nodeName: string,
  envName: string,
  highlightEnvs: readonly string[],
): CardEnvironmentKind | null => {
  if (nodeName === "Environment" && highlightEnvs.includes(envName))
    return null;
  const specific = CARD_ENV_NODE_KIND[nodeName];
  if (specific) return specific;
  if (nodeName === "Environment" && CODE_LIKE_ENV_NAMES.has(envName)) {
    return "environment";
  }
  return null;
};

/**
 * Alignment environments: shown as centered / left / right editable text with
 * the `\begin{…}`/`\end{…}` marker lines hidden, not as a raw frame. The
 * content stays inline-editable — only the markup disappears.
 */
export const ALIGNMENT_ENVS: Record<string, "left" | "center" | "right"> = {
  center: "center",
  flushleft: "left",
  flushright: "right",
};

/**
 * Named prose environments shown as a labelled block (marker lines hidden, a
 * small section header above the still-editable content). Value = i18n key
 * (codeEditor:visual.env.*) for the label.
 */
export const NAMED_PROSE_ENVS: Record<string, string> = {
  abstract: "abstract",
  IEEEabstract: "abstract",
  IEEEkeywords: "keywords",
  keywords: "keywords",
  quote: "quote",
  quotation: "quote",
};

/** `\ref`-style pill widgets: wrapper node → pill kind. */
export const PILL_NODES: Record<string, "ref" | "cite" | "label"> = {
  Ref: "ref",
  Cite: "cite",
  Label: "label",
};

/** Raw commands (UnknownCommand → CtrlSeq text) drawn as a page divider. */
export const DIVIDER_COMMANDS = new Set([
  "\\newpage",
  "\\clearpage",
  "\\cleardoublepage",
  "\\pagebreak",
]);

/**
 * Layout/setup commands that carry no prose — collapsed into a small chip.
 * Value = i18n key (codeEditor:visual.*) for a human label, or null to show
 * the bare command name.
 */
export const SETUP_CHIP_COMMANDS: Record<string, string | null> = {
  "\\addcontentsline": null,
  "\\sloppy": null,
  "\\pagestyle": null,
  "\\thispagestyle": null,
  "\\setcounter": null,
  "\\noindent": null,
  "\\vspace": null,
  "\\hspace": null,
  "\\smallskip": null,
  "\\medskip": null,
  "\\bigskip": null,
  "\\hypersetup": null,
  "\\phantomsection": null,
  "\\titleformat": null,
  "\\titlespacing": null,
  "\\small": null,
  "\\footnotesize": null,
  "\\scriptsize": null,
  "\\normalsize": null,
  "\\tiny": null,
  "\\large": null,
  "\\Large": null,
  "\\LARGE": null,
  "\\huge": null,
  "\\Huge": null,
  "\\bfseries": null,
  "\\mdseries": null,
  "\\itshape": null,
  "\\upshape": null,
  "\\slshape": null,
  "\\scshape": null,
  "\\rmfamily": null,
  "\\sffamily": null,
  "\\ttfamily": null,
  "\\normalfont": null,
  "\\color": null,
  "\\column": null,
  "\\hseBackground": null,
  "\\usebackgroundtemplate": null,
  "\\raggedright": null,
  "\\raggedleft": null,
  "\\arraybackslash": null,
  "\\appendix": "appendices",
  "\\tableofcontents": "contents",
  "\\listoffigures": "figuresList",
  "\\listoftables": "tablesList",
  "\\printbibliography": "bibliography",
};

/**
 * Zero-argument declaration commands among the hidden setup chips. The grammar
 * greedily attaches a following `[…]`/`{…}` to these as an argument, so only the
 * control word is hidden — never the (visible) content after it. Everything else
 * in {@link SETUP_CHIP_COMMANDS} takes real arguments and is hidden whole.
 */
export const DECLARATION_COMMANDS = new Set([
  "\\sloppy",
  "\\noindent",
  "\\raggedright",
  "\\raggedleft",
  "\\arraybackslash",
  "\\smallskip",
  "\\medskip",
  "\\bigskip",
  "\\phantomsection",
  "\\small",
  "\\footnotesize",
  "\\scriptsize",
  "\\normalsize",
  "\\tiny",
  "\\large",
  "\\Large",
  "\\LARGE",
  "\\huge",
  "\\Huge",
  "\\bfseries",
  "\\mdseries",
  "\\itshape",
  "\\upshape",
  "\\slshape",
  "\\scshape",
  "\\rmfamily",
  "\\sffamily",
  "\\ttfamily",
  "\\normalfont",
]);

/** Text-symbol commands rendered as their typographic glyph. */
export const TEXT_SYMBOL_COMMANDS: Record<string, string> = {
  "\\ldots": "…",
  "\\dots": "…",
  "\\textendash": "–",
  "\\textemdash": "—",
};

/** Normalized basename used to classify included LaTeX files. */
export const inputBasename = (path: string): string =>
  (path.replace(/\\/g, "/").split("/").pop() ?? path)
    .replace(/\.tex$/i, "")
    .toLocaleLowerCase();

export const isEmbeddedInput = (
  path: string,
  basenames: readonly string[] | undefined,
): boolean =>
  basenames?.some(
    (basename) => inputBasename(basename) === inputBasename(path),
  ) ?? false;
