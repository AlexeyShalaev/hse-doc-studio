import type { EditorSelection } from "@codemirror/state";

/**
 * Overleaf-style reveal rule: a construct shows its raw LaTeX markup while any
 * selection range touches it (boundary contact counts, so arrowing up to a
 * hidden `\textbf{` reveals it before the cursor would have to jump over it).
 */
export const touchesSelection = (
  selection: EditorSelection,
  from: number,
  to: number,
): boolean => selection.ranges.some((r) => r.to >= from && r.from <= to);

/**
 * Strict-interior variant: boundary contact does NOT count. Used for the
 * preamble banner — the initial cursor sits at position 0, which merely
 * touches the preamble zone and must not auto-expand it on open.
 */
export const insideSelection = (
  selection: EditorSelection,
  from: number,
  to: number,
): boolean => selection.ranges.some((r) => r.to > from && r.from < to);
