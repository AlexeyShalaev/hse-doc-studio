import {
  Facet,
  RangeSetBuilder,
  StateEffect,
  StateField,
  type EditorState,
  type Extension,
} from "@codemirror/state";
import {
  forceLinting,
  lintGutter,
  linter,
  type Diagnostic,
} from "@codemirror/lint";
import {
  Decoration,
  ViewPlugin,
  WidgetType,
  type DecorationSet,
  type EditorView,
  type ViewUpdate,
} from "@codemirror/view";
import { i18n } from "@shared/lib";
import type { DiagnosticClickInfo, EditorDiagnostic } from "./types";

type InlineClickHandler = (info: DiagnosticClickInfo) => void;

/** Per-editor handler invoked when an inline diagnostic message is clicked. */
export const inlineDiagnosticClickFacet = Facet.define<
  InlineClickHandler,
  InlineClickHandler | null
>({
  combine: (handlers) => handlers[0] ?? null,
});

/**
 * Externally-supplied diagnostics (compile / GOST check findings) live in their
 * own StateField and are surfaced through a dedicated `linter()` source. This
 * coexists with the language pack's live structural linter — both sources are
 * merged by `@codemirror/lint`, whereas `setDiagnostics` would clobber them.
 */
const setExternalDiagnostics = StateEffect.define<EditorDiagnostic[]>();

export const externalDiagnosticsField = StateField.define<EditorDiagnostic[]>({
  create: () => [],
  update(value, tr) {
    for (const effect of tr.effects) {
      if (effect.is(setExternalDiagnostics)) return effect.value;
    }
    return value;
  },
});

const SEVERITY_RANK: Record<EditorDiagnostic["severity"], number> = {
  info: 0,
  warning: 1,
  error: 2,
};

const clampLine = (line: number, lineCount: number): number =>
  Math.min(Math.max(1, Math.floor(line)), lineCount);

const toCmDiagnostics = (
  items: readonly EditorDiagnostic[],
  state: EditorState,
): Diagnostic[] => {
  const lineCount = state.doc.lines;
  return items
    .filter((d) => Number.isFinite(d.line) && d.line >= 1)
    .map((d) => {
      // Clamp to the current doc — findings reflect the last compile and a
      // line can point past EOF after the user trims the file.
      const line = state.doc.line(clampLine(d.line, lineCount));
      const diagnostic: Diagnostic = {
        from: line.from,
        to: line.to,
        severity: d.severity,
        message: d.message,
      };
      if (d.source !== undefined) diagnostic.source = d.source;
      return diagnostic;
    });
};

const externalDiagnosticsChanged = (update: ViewUpdate): boolean =>
  update.state.field(externalDiagnosticsField) !==
  update.startState.field(externalDiagnosticsField);

/** The full diagnostics stack: state, the external linter source, and the gutter. */
export const externalDiagnosticsExtension: Extension = [
  externalDiagnosticsField,
  linter(
    (view) =>
      toCmDiagnostics(view.state.field(externalDiagnosticsField), view.state),
    // Without this, `@codemirror/lint`'s `force()` no-ops once an initial lint
    // pass has run (it only fires when a lint is already scheduled). Telling it
    // our field changed reschedules the pass so new findings actually render.
    { needsRefresh: externalDiagnosticsChanged },
  ),
  lintGutter(),
];

/** Push a fresh set of external diagnostics and re-run the gutter immediately. */
export const applyExternalDiagnostics = (
  view: EditorView,
  diagnostics: readonly EditorDiagnostic[],
): void => {
  view.dispatch({ effects: setExternalDiagnostics.of([...diagnostics]) });
  forceLinting(view);
};

// ── Inline diagnostics (Error-Lens style) ──────────────────────────────────

const SEVERITY_PREFIX: Record<EditorDiagnostic["severity"], string> = {
  error: "✕",
  warning: "▸",
  info: "ℹ",
};

class InlineDiagnosticWidget extends WidgetType {
  constructor(
    readonly text: string,
    readonly severity: EditorDiagnostic["severity"],
    readonly line: number,
  ) {
    super();
  }

  override eq(other: InlineDiagnosticWidget): boolean {
    return (
      other.text === this.text &&
      other.severity === this.severity &&
      other.line === this.line
    );
  }

  override toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = `cm-inlineDiag cm-inlineDiag-${this.severity}`;
    span.textContent = this.text;
    const onClick = view.state.facet(inlineDiagnosticClickFacet);
    if (onClick) {
      span.style.cursor = "pointer";
      span.style.pointerEvents = "auto";
      span.title = i18n.t("codeEditor:diagnostics.actionsTitle");
      span.addEventListener("mousedown", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const rect = span.getBoundingClientRect();
        onClick({ line: this.line, left: rect.left, bottom: rect.bottom });
      });
    } else {
      span.setAttribute("aria-hidden", "true");
    }
    return span;
  }
}

const buildInlineDecorations = (state: EditorState): DecorationSet => {
  const diagnostics = state.field(externalDiagnosticsField);
  if (diagnostics.length === 0) return Decoration.none;

  const lineCount = state.doc.lines;
  const byLine = new Map<number, EditorDiagnostic[]>();
  for (const d of diagnostics) {
    if (!Number.isFinite(d.line) || d.line < 1) continue;
    const lineNo = clampLine(d.line, lineCount);
    const list = byLine.get(lineNo);
    if (list) list.push(d);
    else byLine.set(lineNo, [d]);
  }

  const builder = new RangeSetBuilder<Decoration>();
  const entries = [...byLine.entries()].sort((a, b) => a[0] - b[0]);
  for (const [lineNo, items] of entries) {
    const worst = items.reduce<EditorDiagnostic["severity"]>(
      (acc, d) =>
        SEVERITY_RANK[d.severity] > SEVERITY_RANK[acc] ? d.severity : acc,
      "info",
    );
    const primary = items.find((d) => d.severity === worst) ?? items[0];
    if (!primary) continue;
    const extra = items.length > 1 ? ` (+${String(items.length - 1)})` : "";
    const text = `${SEVERITY_PREFIX[worst]} ${primary.message}${extra}`;
    const line = state.doc.line(lineNo);
    builder.add(
      line.to,
      line.to,
      Decoration.widget({
        widget: new InlineDiagnosticWidget(text, worst, lineNo),
        side: 1,
      }),
    );
  }
  return builder.finish();
};

/** Renders each diagnosed line's message inline at the end of the line. */
export const inlineDiagnosticsExtension: Extension = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = buildInlineDecorations(view.state);
    }

    update(update: ViewUpdate): void {
      if (update.docChanged || externalDiagnosticsChanged(update)) {
        this.decorations = buildInlineDecorations(update.state);
      }
    }
  },
  { decorations: (plugin) => plugin.decorations },
);
