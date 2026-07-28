import {
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completionKeymap,
} from "@codemirror/autocomplete";
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
} from "@codemirror/commands";
import {
  bracketMatching,
  foldGutter,
  foldKeymap,
  indentOnInput,
  syntaxTree,
} from "@codemirror/language";
import { html } from "@codemirror/lang-html";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { yaml } from "@codemirror/lang-yaml";
import { lintKeymap } from "@codemirror/lint";
import {
  highlightSelectionMatches,
  search,
  searchKeymap,
} from "@codemirror/search";
import { Compartment, EditorState, type Extension } from "@codemirror/state";
import {
  crosshairCursor,
  drawSelection,
  dropCursor,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
  rectangularSelection,
} from "@codemirror/view";
import { latex } from "codemirror-lang-latex";
import { sectionFoldService, wrapInEnvironment } from "./commands";
import {
  editorCommands,
  selectionFormatState,
  toggleBold,
  toggleItalic,
} from "./formatCommands";
import { visualLatexExtension, type VisualCallbacks } from "./visual";
import { preambleCollapsedField } from "./visual/atomicBlocks";
import type { VisualEditorOptions } from "./types";
import {
  externalDiagnosticsExtension,
  inlineDiagnosticClickFacet,
  inlineDiagnosticsExtension,
} from "./diagnostics";
import { hseEditorTheme, hseHighlightExtension } from "./cmTheme";
import { latexSnippetExtension } from "./snippets";
import { computeOutline, outlineActiveIndex } from "./outline";
import { computeStats } from "./stats";
import type {
  DiagnosticClickInfo,
  EditorFormatState,
  EditorLanguage,
  EditorStats,
  OutlineState,
} from "./types";

// Module-scope compartments → stable identities for runtime reconfiguration of
// line-wrap, read-only, inline diagnostics and the visual mode without
// recreating the EditorView (which would drop undo history and scroll).
export const wrapCompartment = new Compartment();
export const readOnlyCompartment = new Compartment();
export const inlineDiagnosticsCompartment = new Compartment();
export const visualCompartment = new Compartment();
// Code-mode gutters (line numbers, folding) go away in the visual mode — the
// base theme pins `.cm-gutter { display:flex !important }`, so they must be
// removed from the config rather than hidden with CSS.
export const gutterCompartment = new Compartment();

export const codeGutterExtensions = (): Extension[] => [
  lineNumbers(),
  highlightActiveLineGutter(),
  foldGutter(),
];

// LaTeX has its own dedicated branch below (autocomplete/snippets/tooltips);
// this only covers the non-LaTeX grammars. `plain` (and any future extension
// with no grammar here) falls back to no language — just brackets/close-tags.
const LANGUAGE_EXTENSIONS: Partial<Record<EditorLanguage, Extension>> = {
  json: json(),
  yaml: yaml(),
  html: html(),
  markdown: markdown(),
};

type BuildExtensionsOptions = {
  language: EditorLanguage;
  wrapLines: boolean;
  readOnly: boolean;
  visualMode: boolean;
  visualOptions?: VisualEditorOptions;
  visualCallbacks?: VisualCallbacks;
  inlineDiagnostics: boolean;
  onChange: (value: string) => void;
  onSave: (value: string) => void;
  onInlineDiagnosticClick?: (info: DiagnosticClickInfo) => void;
  onStats?: (stats: EditorStats) => void;
  onFormatState?: (state: EditorFormatState) => void;
  onOutline?: (outline: OutlineState) => void;
  onModClick?: (line: number) => void;
  ariaLabel?: string;
};

export const buildExtensions = ({
  language,
  wrapLines,
  readOnly,
  visualMode,
  visualOptions,
  visualCallbacks,
  inlineDiagnostics,
  onChange,
  onSave,
  onInlineDiagnosticClick,
  onStats,
  onFormatState,
  onOutline,
  onModClick,
  ariaLabel,
}: BuildExtensionsOptions): Extension[] => {
  const visualActive = visualMode && language === "latex";
  let formatStateFrame = 0;
  let lastFormatState: EditorFormatState | null = null;
  let outlineFrame = 0;
  let lastOutline: OutlineState | null = null;
  // Doc totals (chars/words) are O(doc) to compute — cache per doc identity
  // so pure caret movement reuses them.
  let statsDoc: unknown = null;
  let statsTotals: { chars: number; words: number } | null = null;
  const extensions: Extension[] = [
    ...(ariaLabel
      ? [
          EditorView.contentAttributes.of({
            "aria-label": ariaLabel,
            "aria-multiline": "true",
          }),
        ]
      : []),
    gutterCompartment.of(visualActive ? [] : codeGutterExtensions()),
    drawSelection(),
    dropCursor(),
    EditorState.allowMultipleSelections.of(true),
    indentOnInput(),
    highlightActiveLine(),
    highlightSelectionMatches(),
    rectangularSelection(),
    crosshairCursor(),
    history(),
    search({ top: true }),
    sectionFoldService,
    hseHighlightExtension,
    hseEditorTheme,
    externalDiagnosticsExtension,
    inlineDiagnosticsCompartment.of(
      inlineDiagnostics ? inlineDiagnosticsExtension : [],
    ),
    wrapCompartment.of(wrapLines ? EditorView.lineWrapping : []),
    readOnlyCompartment.of(EditorState.readOnly.of(readOnly)),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) onChange(update.state.doc.toString());
      if (onStats && (update.docChanged || update.selectionSet)) {
        const stats = computeStats(
          update.state,
          statsDoc === update.state.doc ? statsTotals : null,
        );
        statsDoc = update.state.doc;
        statsTotals = { chars: stats.chars, words: stats.words };
        onStats(stats);
      }
      // Format state feeds the visual-mode toolbar only — the field presence
      // check keeps code mode free of full-document tree walks.
      const visualNow =
        update.state.field(preambleCollapsedField, false) !== undefined;
      if (onFormatState && visualNow) {
        const visualBefore =
          update.startState.field(preambleCollapsedField, false) !== undefined;
        if (
          update.docChanged ||
          update.selectionSet ||
          !visualBefore || // just toggled into visual → seed the toolbar
          // The parse advances asynchronously after load — the fields
          // counter must catch up once the tree is complete.
          syntaxTree(update.state) !== syntaxTree(update.startState)
        ) {
          // rAF-throttled: the format state walks the syntax tree, which is
          // too heavy to run for every keystroke of a fast typist.
          cancelAnimationFrame(formatStateFrame);
          formatStateFrame = requestAnimationFrame(() => {
            const next = selectionFormatState(update.view.state);
            if (
              next.bold === lastFormatState?.bold &&
              next.italic === lastFormatState.italic &&
              next.underline === lastFormatState.underline &&
              next.monospace === lastFormatState.monospace &&
              next.heading === lastFormatState.heading &&
              next.list === lastFormatState.list &&
              next.fieldsRemaining === lastFormatState.fieldsRemaining
            ) {
              return; // unchanged → skip the React re-render entirely
            }
            lastFormatState = next;
            onFormatState(next);
          });
        }
      }
      // Headings outline (Word-style navigation pane): items change with the
      // tree, the active section with the caret — both memoized/cheap.
      if (onOutline && visualNow) {
        const visualBefore =
          update.startState.field(preambleCollapsedField, false) !== undefined;
        if (
          update.docChanged ||
          update.selectionSet ||
          !visualBefore ||
          syntaxTree(update.state) !== syntaxTree(update.startState)
        ) {
          cancelAnimationFrame(outlineFrame);
          outlineFrame = requestAnimationFrame(() => {
            const items = computeOutline(update.view.state);
            const activeIndex = outlineActiveIndex(
              items,
              update.view.state.selection.main.head,
            );
            if (
              lastOutline?.items === items &&
              lastOutline.activeIndex === activeIndex
            ) {
              return;
            }
            lastOutline = { items, activeIndex };
            onOutline(lastOutline);
          });
        }
      }
    }),
    keymap.of([
      {
        key: "Mod-s",
        preventDefault: true,
        run: (view) => {
          onSave(view.state.doc.toString());
          return true;
        },
      },
      // Toggle common LaTeX markup (wrap the selection, or unwrap when the
      // cursor already sits inside a matching command). These shadow any
      // browser bold/italic defaults inside the editor (preventDefault) and
      // work with multiple selections.
      {
        key: "Mod-b",
        preventDefault: true,
        run: toggleBold,
      },
      {
        key: "Mod-i",
        preventDefault: true,
        run: toggleItalic,
      },
      {
        key: "Mod-u",
        preventDefault: true,
        run: editorCommands.underline,
      },
      {
        key: "Mod-Shift-e",
        preventDefault: true,
        run: wrapInEnvironment("equation"),
      },
      indentWithTab,
      ...closeBracketsKeymap,
      ...defaultKeymap,
      ...historyKeymap,
      ...foldKeymap,
      ...completionKeymap,
      ...searchKeymap,
      ...lintKeymap,
    ]),
  ];

  // Only register the click handler (which makes inline messages interactive)
  // when a consumer actually supplies one.
  if (onInlineDiagnosticClick) {
    extensions.push(inlineDiagnosticClickFacet.of(onInlineDiagnosticClick));
  }

  // Ctrl/Cmd+click → emit the clicked line (SyncTeX forward jump). Returning
  // true pre-empts CodeMirror's own modifier-click (which adds a cursor).
  if (onModClick) {
    extensions.push(
      EditorView.domEventHandlers({
        mousedown: (event, view) => {
          if (!(event.ctrlKey || event.metaKey)) return false;
          const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
          if (pos == null) return false;
          onModClick(view.state.doc.lineAt(pos).number);
          event.preventDefault();
          return true;
        },
      }),
    );
  }

  if (language === "latex") {
    // The language pack brings close-brackets, bracket-matching,
    // auto-close-tags, hover tooltips and a live structural linter, and it
    // ALWAYS registers its completion source through languageData. Its
    // enableAutocomplete flag is disabled on purpose: that flag only adds an
    // `autocompletion({override})` wrapper which would silence every other
    // languageData source (our RU snippets, the visual-mode slash menu).
    // A plain autocompletion() composes them all instead.
    extensions.push(
      latex({
        enableAutocomplete: false,
        enableTooltips: true,
        enableLinting: true,
        autoCloseBrackets: true,
        autoCloseTags: true,
      }),
      autocompletion(),
      latexSnippetExtension,
    );
  } else {
    // Non-LaTeX grammars tag tokens with the same standard @lezer/highlight
    // tags `hseHighlightStyle` already maps (keyword, string, comment, ...),
    // so they pick up the theme with no extra styling work.
    const grammar = LANGUAGE_EXTENSIONS[language];
    extensions.push(
      ...(grammar ? [grammar] : []),
      bracketMatching(),
      closeBrackets(),
      autocompletion(),
    );
  }

  // Must come after the language extension: the visual decorations' state
  // field reads the syntax tree during updates, and field update order follows
  // extension order — this way it always sees the freshly advanced parse.
  extensions.push(
    visualCompartment.of(
      visualActive ? visualLatexExtension(visualOptions, visualCallbacks) : [],
    ),
  );

  return extensions;
};
