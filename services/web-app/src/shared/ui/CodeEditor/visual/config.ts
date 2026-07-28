import { Facet } from "@codemirror/state";
import type { VisualEmbeddedInputKind, VisualHeadingAlignment } from "../types";

/**
 * Per-instance options of the visual mode, provided by the host application
 * (feature layer) and read by the decoration builders via a facet.
 */
export type VisualConfig = {
  /**
   * Known zero-argument macro expansions (`hseProjectName` → «Ядро …»),
   * usually parsed from the project's `common/meta.tex` / `commands.tex`.
   * Values are plain text; a value of the form `\hseFill{hint}` marks an
   * unfilled field and renders as a placeholder.
   */
  macros: Record<string, string>;
  /** Show full-line comments dimmed instead of collapsing them into chips. */
  showComments: boolean;
  /** Comment-run prefixes rendered as hint callouts (e.g. «Подсказка:»). */
  hintPrefixes: string[];
  /** Environments rendered as highlighted «образец» blocks (hseExample). */
  highlightEnvs: string[];
  /** Heading alignment, keyed by the visual heading level. */
  headingAlignments?: Partial<Record<number, VisualHeadingAlignment>>;
  /** Basenames of full-line inputs represented by protected block widgets. */
  embeddedInputBasenames?: string[];
  /** Semantic renderer kind, keyed by exact input path or basename. */
  embeddedInputKinds?: Record<string, VisualEmbeddedInputKind>;
  /** Loaded protected-input source, keyed by exact input path or basename. */
  embeddedInputSources?: Record<string, string>;
};

const DEFAULT_CONFIG: VisualConfig = {
  macros: {},
  showComments: false,
  hintPrefixes: [],
  highlightEnvs: [],
  headingAlignments: {},
  embeddedInputBasenames: [],
  embeddedInputKinds: {},
  embeddedInputSources: {},
};

/**
 * Host callbacks for the visual bundle. Passed through extension factories
 * as plain closures — never through facets (facet values are data-only).
 */
export type VisualCallbacks = {
  onPasteTransformed?: (() => void) | undefined;
  onOpenFile?: ((path: string) => void) | undefined;
  /** Resolve an `\includegraphics{…}` path to a same-origin image URL. */
  resolveAssetUrl?: ((path: string) => string | null) | undefined;
  /** Upload a pasted/dropped image; resolves to the path for the snippet. */
  onDropImage?: ((file: File) => Promise<string | null>) | undefined;
  /** The upload succeeded but the editor was gone (file switched) — the
   *  figure snippet was NOT inserted. */
  onImageInsertSkipped?: (() => void) | undefined;
  /**
   * Open a structured editor for a table environment. `source` is the table's
   * raw LaTeX; `commit(next)` replaces it with the regenerated LaTeX. Without
   * this callback a table card falls back to reveal-the-source editing.
   */
  onEditTable?:
    | ((source: string, commit: (next: string) => void) => void)
    | undefined;
  /**
   * Open a structured manager for a `thebibliography` environment. `source` is
   * its raw LaTeX; `commit(next)` replaces it with the regenerated LaTeX. The
   * inline list still prettifies without it; only the «Управлять» / «Добавить»
   * buttons need it.
   */
  onEditBibliography?:
    | ((source: string, commit: (next: string) => void) => void)
    | undefined;
};

export const visualConfigFacet = Facet.define<VisualConfig, VisualConfig>({
  combine: (values) => values[0] ?? DEFAULT_CONFIG,
});

/** Stable host callbacks needed by state-field block widgets. */
export const visualCallbacksFacet = Facet.define<
  VisualCallbacks,
  VisualCallbacks
>({
  combine: (values) => values[0] ?? {},
});
