export type EditorLanguage =
  | "latex"
  | "json"
  | "yaml"
  | "html"
  | "markdown"
  | "plain";

/**
 * A deterministic text substitution carried by a diagnostic — powers a
 * one-click quick-fix (replace `search` with `replace`, on `line` if set).
 */
export type EditorQuickFix = {
  search: string;
  replace: string;
  line: number | null;
  title: string | null;
};

/**
 * A line-anchored, CodeMirror-agnostic diagnostic. Callers (features) build
 * these from domain data (check findings, compile errors) without ever
 * importing `@codemirror/lint`, keeping the editor a pure shared primitive.
 */
export type EditorDiagnostic = {
  line: number;
  severity: "info" | "warning" | "error";
  message: string;
  source?: string;
  /** Optional deterministic fix for a one-click action in the diagnostic menu. */
  fix?: EditorQuickFix;
};

/**
 * A request to scroll to / select a 1-based line. The `token` makes repeated
 * requests for the same line distinct so the reveal effect re-fires.
 */
export type RevealRequest = {
  line: number;
  token: number;
};

/** Where an inline diagnostic was clicked (1-based line + viewport coords). */
export type DiagnosticClickInfo = {
  line: number;
  left: number;
  bottom: number;
};

/** Live document/cursor stats for a status bar (words, chars, caret, selection). */
export type EditorStats = {
  chars: number;
  words: number;
  line: number;
  column: number;
  selectedChars: number;
  selectedWords: number;
};

/**
 * Formatting actions exposed to toolbars. String ids (not CodeMirror
 * commands) keep the editor a pure shared primitive — same reasoning as
 * `EditorDiagnostic`.
 */
export type EditorCommandId =
  | "bold"
  | "italic"
  | "underline"
  | "monospace"
  | "bulletList"
  | "numberedList"
  | "inlineMath"
  | "displayMath"
  | "insert:figure"
  | "insert:table"
  | "insert:quote"
  | "insert:footnote"
  | "insert:citation"
  | "insert:pageBreak"
  | "heading:chapter"
  | "heading:section"
  | "heading:subsection"
  | "heading:subsubsection"
  | "heading:none"
  | "nextField"
  | "prevField";

/**
 * What formatting applies at the current selection — drives toolbar active
 * states, the heading dropdown value and the «осталось полей» counter.
 */
export type EditorFormatState = {
  bold: boolean;
  italic: boolean;
  underline: boolean;
  monospace: boolean;
  heading: "chapter" | "section" | "subsection" | "subsubsection" | null;
  list: "itemize" | "enumerate" | "description" | null;
  /** Unfilled template fields (\hseFill + empty meta macros) in the document. */
  fieldsRemaining: number;
};

/** A heading in the document outline (Word-style navigation pane). */
export type OutlineItem = {
  /** Visual level 1..5 (chapter → subparagraph). */
  level: number;
  title: string;
  /** 1-based line of the heading (for the reveal/goto mechanism). */
  line: number;
  from: number;
};

/** Outline payload delivered through `onOutline`. */
export type OutlineState = {
  items: OutlineItem[];
  /** Index of the heading whose section contains the caret (-1 = none). */
  activeIndex: number;
};

/** Imperative handle for external toolbars (populated via `controllerRef`). */
export type CodeEditorController = {
  exec: (id: EditorCommandId) => boolean;
  undo: () => boolean;
  redo: () => boolean;
  focus: () => void;
};

export type VisualHeadingAlignment = "left" | "center" | "right";

/** Semantic renderer used for a protected, source-backed LaTeX input. */
export type VisualEmbeddedInputKind =
  | "titlePages"
  | "vkrTitle"
  | "requirementsTable"
  | "changeLog"
  | "generic";

/** Host-provided options for the visual mode (see `visualMode`). */
export type VisualEditorOptions = {
  /**
   * Zero-argument macro expansions (name without backslash → plain-text
   * value) rendered as Word-style fields; a `\hseFill{hint}` value marks an
   * unfilled field.
   */
  macros?: Record<string, string>;
  /** Show full-line comments dimmed instead of collapsing them into chips. */
  showComments?: boolean;
  /**
   * Full-line comment runs starting with one of these prefixes render as
   * readable hint callouts instead of collapsed chips (e.g. «Подсказка:»).
   */
  hintPrefixes?: string[];
  /**
   * Environment names rendered as highlighted «образец» blocks (banner +
   * tinted lines) instead of a raw frame (e.g. the pack's hseExample).
   */
  highlightEnvs?: string[];
  /** Heading alignment derived from the document's real LaTeX style file. */
  headingAlignments?: Partial<Record<number, VisualHeadingAlignment>>;
  /** Full-line `\input`s rendered as protected generated blocks, by basename. */
  embeddedInputBasenames?: string[];
  /**
   * Renderer kind for each input. Keys may be the exact path written in the
   * document or a normalized basename (exact path wins).
   */
  embeddedInputKinds?: Record<string, VisualEmbeddedInputKind>;
  /**
   * Loaded source for protected inputs. Keys may be the exact path written in
   * the document or a normalized basename (exact path wins). This lets
   * semantic widgets reflect the real included file without copying it into
   * the editable document.
   */
  embeddedInputSources?: Record<string, string>;
};

export type CodeEditorProps = {
  value: string;
  onChange?: (value: string) => void;
  onSave?: (value: string) => void;
  readOnly?: boolean;
  wrapLines?: boolean;
  /**
   * Overleaf-style visual editing: LaTeX markup is hidden/styled via
   * decorations, revealed around the cursor. Only effective for `latex`.
   */
  visualMode?: boolean;
  /** Options for the visual mode (macro expansions, comment visibility). */
  visualOptions?: VisualEditorOptions;
  /** Receives an imperative controller once the editor view exists. */
  controllerRef?: { current: CodeEditorController | null };
  language?: EditorLanguage;
  diagnostics?: EditorDiagnostic[];
  /** Show each diagnosed line's message inline (Error-Lens style). Default on. */
  inlineDiagnostics?: boolean;
  /** Imperative scroll-to-line request. */
  reveal?: RevealRequest;
  /** Called when an inline diagnostic message is clicked (opens an action menu). */
  onDiagnosticClick?: (info: DiagnosticClickInfo) => void;
  /** Called on doc/selection change with live word/char/caret stats. */
  onStats?: (stats: EditorStats) => void;
  /** Called (rAF-throttled) with the formatting state at the selection. */
  onFormatState?: (state: EditorFormatState) => void;
  /** Called (rAF-throttled, visual mode) with the headings outline. */
  onOutline?: (outline: OutlineState) => void;
  /** Called when a paste was auto-escaped for LaTeX (visual mode only). */
  onPasteTransformed?: () => void;
  /**
   * Called when the user clicks an `\input{…}` file chip in visual mode
   * (path exactly as written in the source). Alt+click always reveals the
   * raw command instead; without this callback a plain click reveals too.
   */
  onOpenFile?: (path: string) => void;
  /**
   * Resolve an `\includegraphics{…}` path (as written in the source) to a
   * same-origin image URL for the inline preview; null → filename pill.
   * Must be cheap and synchronous — it runs during decoration builds.
   */
  resolveAssetUrl?: (path: string) => string | null;
  /**
   * Upload a pasted/dropped image and resolve to the path to embed in the
   * inserted figure snippet (null = failed, nothing is inserted).
   */
  onDropImage?: (file: File) => Promise<string | null>;
  /** Upload succeeded but the editor was unmounted — no snippet inserted. */
  onImageInsertSkipped?: () => void;
  /**
   * Open a structured table editor for a table environment (visual mode).
   * `source` is the table's raw LaTeX; `commit(next)` replaces it with the
   * regenerated LaTeX. Omit it to fall back to reveal-the-source editing.
   */
  onEditTable?: (source: string, commit: (next: string) => void) => void;
  /**
   * Open a structured manager for a `thebibliography` environment (visual mode).
   * `source` is its raw LaTeX; `commit(next)` replaces it. The inline list still
   * prettifies without it; only «Управлять» / «Добавить» need it.
   */
  onEditBibliography?: (source: string, commit: (next: string) => void) => void;
  /** Ctrl/Cmd+click on a line → its 1-based number (e.g. SyncTeX forward jump). */
  onModClick?: (line: number) => void;
  className?: string;
  ariaLabel?: string;
};
