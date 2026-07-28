import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";
import type { Extension } from "@codemirror/state";

/**
 * Editor chrome theme. Every color is a `var(--*)` reference into the app's
 * design system, so the editor restyles itself for the dark / light /
 * blueprint themes purely via `[data-theme]` — no CodeMirror reconfigure.
 */
export const hseEditorTheme: Extension = EditorView.theme({
  "&": {
    color: "var(--fg-0)",
    backgroundColor: "var(--bg-0)",
    height: "100%",
    fontSize: "12.5px",
  },
  ".cm-scroller": {
    fontFamily: "var(--font-mono)",
    lineHeight: "1.6",
    overflow: "auto",
  },
  ".cm-content": {
    caretColor: "var(--accent)",
    padding: "10px 0",
  },
  ".cm-cursor, .cm-dropCursor": {
    borderLeftColor: "var(--accent)",
    borderLeftWidth: "2px",
  },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
    {
      backgroundColor: "var(--accent-soft)",
    },
  ".cm-activeLine": {
    backgroundColor: "var(--bg-elev)",
  },
  ".cm-selectionMatch": {
    backgroundColor: "var(--accent-soft)",
  },
  "&.cm-focused .cm-matchingBracket, .cm-matchingBracket": {
    backgroundColor: "transparent",
    outline: "1px solid var(--accent-line)",
    borderRadius: "2px",
    color: "var(--fg-0)",
  },
  ".cm-nonmatchingBracket": { color: "var(--c-err)" },

  // Gutters
  ".cm-gutters": {
    backgroundColor: "var(--bg-1)",
    color: "var(--fg-3)",
    border: "none",
    borderRight: "1px solid var(--border)",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "var(--bg-2)",
    color: "var(--fg-1)",
  },
  ".cm-lineNumbers .cm-gutterElement": {
    fontVariantNumeric: "tabular-nums",
    padding: "0 8px 0 14px",
    minWidth: "30px",
  },
  ".cm-foldGutter .cm-gutterElement": { color: "var(--fg-3)" },

  // Search / replace panel
  ".cm-panels": { backgroundColor: "var(--bg-1)", color: "var(--fg-1)" },
  ".cm-panels.cm-panels-top": { borderBottom: "1px solid var(--border)" },
  ".cm-panel.cm-search": {
    padding: "6px 8px",
    fontFamily: "var(--font-sans)",
    fontSize: "12px",
  },
  ".cm-panel.cm-search input, .cm-panel.cm-search button, .cm-textfield": {
    backgroundColor: "var(--bg-2)",
    color: "var(--fg-0)",
    border: "1px solid var(--border)",
    borderRadius: "var(--r-2)",
    padding: "2px 6px",
  },
  ".cm-panel.cm-search label": { color: "var(--fg-2)" },
  ".cm-button": {
    backgroundImage: "none",
    backgroundColor: "var(--bg-2)",
    color: "var(--fg-1)",
    border: "1px solid var(--border)",
    borderRadius: "var(--r-2)",
  },
  ".cm-searchMatch": {
    backgroundColor: "var(--c-warn-soft)",
    outline: "1px solid color-mix(in oklab, var(--c-warn) 50%, transparent)",
  },
  ".cm-searchMatch.cm-searchMatch-selected": {
    backgroundColor: "var(--accent-soft)",
  },

  // Autocomplete tooltip
  ".cm-tooltip": {
    backgroundColor: "var(--bg-1)",
    border: "1px solid var(--border)",
    borderRadius: "var(--r-3)",
    boxShadow: "var(--shadow-pop, 0 12px 40px rgba(0,0,0,0.45))",
    color: "var(--fg-0)",
    overflow: "hidden",
  },
  ".cm-tooltip.cm-tooltip-autocomplete > ul": {
    fontFamily: "var(--font-mono)",
    fontSize: "12px",
    maxHeight: "16em",
  },
  ".cm-tooltip-autocomplete > ul > li": { padding: "3px 8px" },
  ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
    backgroundColor: "var(--accent-soft)",
    color: "var(--fg-0)",
  },
  ".cm-completionLabel": { color: "var(--fg-0)" },
  ".cm-completionMatchedText": {
    color: "var(--accent)",
    textDecoration: "none",
    fontWeight: "600",
  },
  ".cm-completionDetail": { color: "var(--fg-3)", fontStyle: "italic" },
  ".cm-completionIcon": { color: "var(--fg-2)", opacity: "0.9" },

  // Lint / diagnostics
  ".cm-diagnostic": {
    fontFamily: "var(--font-mono)",
    fontSize: "11.5px",
    padding: "4px 8px",
    borderRadius: "var(--r-2)",
  },
  ".cm-diagnostic-error": { borderLeft: "3px solid var(--c-err)" },
  ".cm-diagnostic-warning": { borderLeft: "3px solid var(--c-warn)" },
  ".cm-diagnostic-info": { borderLeft: "3px solid var(--c-info)" },
  ".cm-diagnosticSource": { color: "var(--fg-3)", fontSize: "10.5px" },
  ".cm-lintRange-error": {
    backgroundImage: "none",
    textDecoration: "underline wavy var(--c-err)",
  },
  ".cm-lintRange-warning": {
    backgroundImage: "none",
    textDecoration: "underline wavy var(--c-warn)",
  },
  ".cm-lintRange-info": {
    backgroundImage: "none",
    textDecoration: "underline dotted var(--c-info)",
  },
  ".cm-lint-marker-error": { color: "var(--c-err)" },
  ".cm-lint-marker-warning": { color: "var(--c-warn)" },
  ".cm-lint-marker-info": { color: "var(--c-info)" },

  // Inline diagnostics (Error-Lens style) shown at the end of a line
  ".cm-inlineDiag": {
    paddingLeft: "1.6em",
    fontSize: "11px",
    fontStyle: "italic",
    opacity: "0.92",
    whiteSpace: "pre",
    pointerEvents: "none",
    userSelect: "none",
  },
  ".cm-inlineDiag-error": { color: "var(--c-err)" },
  ".cm-inlineDiag-warning": { color: "var(--c-warn)" },
  ".cm-inlineDiag-info": { color: "var(--c-info)" },
});

/**
 * Token colors mirroring the legacy `highlightTex` palette: commands → accent,
 * comments → faint italic, delimiters → primary fg, numbers/labels → info,
 * strings → warn. Tags are standard `@lezer/highlight` tags, so every grammar
 * built on them (LaTeX via `codemirror-lang-latex`, plus the JSON/YAML/HTML/
 * Markdown packs in `cmExtensions.ts`) picks up this same palette for free.
 */
export const hseHighlightStyle: HighlightStyle = HighlightStyle.define([
  {
    tag: [
      t.controlKeyword,
      t.keyword,
      t.tagName,
      t.moduleKeyword,
      t.macroName,
      t.typeName,
    ],
    color: "var(--accent)",
  },
  {
    tag: [t.comment, t.lineComment, t.blockComment],
    color: "var(--fg-3)",
    fontStyle: "italic",
  },
  {
    tag: [
      t.brace,
      t.bracket,
      t.squareBracket,
      t.paren,
      t.punctuation,
      t.separator,
      t.angleBracket,
    ],
    color: "var(--fg-0)",
  },
  {
    tag: [t.number, t.integer, t.float, t.unit, t.bool, t.null],
    color: "var(--c-info)",
  },
  {
    tag: [
      t.string,
      t.special(t.string),
      t.regexp,
      t.attributeValue,
      t.monospace,
    ],
    color: "var(--c-warn)",
  },
  {
    tag: [t.labelName, t.atom, t.attributeName, t.className, t.namespace],
    color: "var(--c-info)",
  },
  { tag: [t.variableName, t.propertyName, t.content], color: "var(--fg-0)" },
  {
    tag: [
      t.operator,
      t.derefOperator,
      t.definitionOperator,
      t.compareOperator,
      t.logicOperator,
      t.arithmeticOperator,
      t.operatorKeyword,
    ],
    color: "var(--fg-1)",
  },
  { tag: t.invalid, color: "var(--c-err)" },
  { tag: [t.heading, t.strong], fontWeight: "600", color: "var(--fg-0)" },
  { tag: t.emphasis, fontStyle: "italic" },
  {
    tag: t.strikethrough,
    color: "var(--fg-3)",
    textDecoration: "line-through",
  },
  { tag: [t.link, t.url], color: "var(--accent)", textDecoration: "underline" },
  {
    tag: [t.meta, t.documentMeta, t.processingInstruction, t.character],
    color: "var(--fg-3)",
  },
  { tag: [t.quote, t.list, t.contentSeparator], color: "var(--fg-3)" },
]);

export const hseHighlightExtension: Extension =
  syntaxHighlighting(hseHighlightStyle);
