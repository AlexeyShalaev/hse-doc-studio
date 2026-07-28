import { syntaxTree } from "@codemirror/language";
import {
  EditorSelection,
  type EditorState,
  type StateCommand,
} from "@codemirror/state";
import type { Command, EditorView } from "@codemirror/view";
import type { SyntaxNode } from "@lezer/common";
import { blockZones, preambleCollapsedField } from "./atomicBlocks";
import { setPreambleCollapsed } from "./effects";

/**
 * Word-like caret behavior around invisible markup:
 *  - Enter inside a heading starts a NEW paragraph below (never splits the
 *    `\section{…}` argument in half);
 *  - Home/End land on the visible text, not before/after hidden braces;
 *  - Backspace at the start of a line that follows a hidden block (a hidden
 *    `\begin`/`\end` line, a collapsed hint, the preamble banner…) never
 *    silently mutates the hidden structure: after a hidden list `\end` it
 *    pulls the line up into the last item (Word behavior), everywhere else it
 *    reveals the hidden block first.
 * Every command falls through (returns false) outside its exact context.
 */

const enclosingSectioning = (
  state: EditorState,
  pos: number,
): SyntaxNode | null => {
  let node: SyntaxNode | null = syntaxTree(state).resolveInner(pos, -1);
  for (; node; node = node.parent) {
    if (node.name === "SectioningCommand") return node;
  }
  return null;
};

/** Enter inside `\section{…}` → open a fresh paragraph under the heading. */
export const insertParagraphAfterHeading: StateCommand = ({
  state,
  dispatch,
}) => {
  if (state.readOnly) return false;
  const range = state.selection.main;
  if (state.selection.ranges.length !== 1 || !range.empty) return false;
  const command = enclosingSectioning(state, range.head);
  if (!command || range.head <= command.from) return false;
  const line = state.doc.lineAt(command.to);
  dispatch(
    state.update({
      changes: { from: line.to, insert: "\n" },
      selection: { anchor: line.to + 1 },
      scrollIntoView: true,
      userEvent: "input",
    }),
  );
  return true;
};

const ITEM_PREFIX_RE = /^(\s*)\\item(\[[^\]]*\])?( ?)/;
const SECTIONING_LINE_RE =
  /^\s*\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?\{/;

/** Visible text start of a line, past hidden `\item ` / `\section{` markup. */
export const homeTargetFor = (state: EditorState, pos: number): number => {
  const line = state.doc.lineAt(pos);
  const item = ITEM_PREFIX_RE.exec(line.text);
  if (item && item[0].length > (item[1]?.length ?? 0)) {
    return line.from + item[0].length;
  }
  const section = SECTIONING_LINE_RE.exec(line.text);
  if (section) return line.from + section[0].length;
  return line.from;
};

/** Visible text end of a line, before a hidden trailing `}` of a heading. */
export const endTargetFor = (state: EditorState, pos: number): number => {
  const line = state.doc.lineAt(pos);
  if (SECTIONING_LINE_RE.test(line.text) && line.text.trimEnd().endsWith("}")) {
    const trimmed = line.from + line.text.trimEnd().length;
    return trimmed - 1;
  }
  return line.to;
};

const onFirstWrapSegment = (view: EditorView, pos: number): boolean =>
  view.moveToLineBoundary(EditorSelection.cursor(pos), false).head ===
  view.state.doc.lineAt(pos).from;

const onLastWrapSegment = (view: EditorView, pos: number): boolean =>
  view.moveToLineBoundary(EditorSelection.cursor(pos), true).head ===
  view.state.doc.lineAt(pos).to;

export const smartHome: Command = (view) => {
  const range = view.state.selection.main;
  if (view.state.selection.ranges.length !== 1 || !range.empty) return false;
  const target = homeTargetFor(view.state, range.head);
  if (target === view.state.doc.lineAt(range.head).from) return false;
  if (!onFirstWrapSegment(view, range.head)) return false;
  if (range.head === target) return false; // already there → default (line start)
  view.dispatch({ selection: { anchor: target }, scrollIntoView: true });
  return true;
};

export const smartEnd: Command = (view) => {
  const range = view.state.selection.main;
  if (view.state.selection.ranges.length !== 1 || !range.empty) return false;
  const target = endTargetFor(view.state, range.head);
  if (target === view.state.doc.lineAt(range.head).to) return false;
  if (!onLastWrapSegment(view, range.head)) return false;
  if (range.head === target) return false; // already there → default (line end)
  view.dispatch({ selection: { anchor: target }, scrollIntoView: true });
  return true;
};

/**
 * Backspace at the start of a line right after a hidden block. The hidden
 * `\end` of a list gets the Word treatment (pull this line's text up into the
 * last item); every other hidden block (hidden `\begin`, hint callout,
 * comment chip, banner, display math, preamble) is revealed instead so the
 * user always sees what the next Backspace would touch.
 */
export const guardBackspaceAfterHiddenBlock: StateCommand = ({
  state,
  dispatch,
}) => {
  if (state.readOnly) return false;
  const range = state.selection.main;
  if (state.selection.ranges.length !== 1 || !range.empty) return false;
  const pos = range.head;
  const line = state.doc.lineAt(pos);
  if (pos !== line.from || pos === 0) return false;
  const zone = blockZones(state).find(
    (z) => z.kind !== "math" && z.to === pos - 1,
  );
  if (!zone) return false;

  // An expanded preamble is plain visible text — nothing is hidden there, so
  // let the default Backspace perform the normal line join.
  if (zone.kind === "preamble" && !state.field(preambleCollapsedField)) {
    return false;
  }

  const mergeTarget =
    zone.kind === "hiddenLine" && zone.marker === "end"
      ? state.doc.lineAt(zone.from)
      : null;
  if (
    mergeTarget &&
    // Only merge into real item content — for an empty or nested list the
    // line before the hidden \end is itself a (hidden) \begin/\end marker,
    // and splicing text there would corrupt the environment.
    !/^\s*\\(?:begin|end)\{/.test(mergeTarget.text)
  ) {
    // Pull the current line's text up into the last item before the \end.
    const text = state.doc.sliceString(pos, line.to);
    const removeTo = Math.min(line.to + 1, state.doc.length);
    const changes = [
      ...(text ? [{ from: zone.from, insert: text }] : []),
      removeTo > pos ? { from: pos, to: removeTo } : { from: pos - 1, to: pos },
    ];
    dispatch(
      state.update({
        changes,
        selection: { anchor: zone.from },
        scrollIntoView: true,
        userEvent: "delete",
      }),
    );
    return true;
  }

  // Reveal the hidden block: a caret inside its range disables the
  // decoration (touch-reveal), so the user sees the raw lines. The preamble
  // needs its collapse flag flipped as well (its reveal is strict-interior).
  dispatch(
    state.update({
      selection: { anchor: zone.to },
      effects: zone.kind === "preamble" ? [setPreambleCollapsed.of(false)] : [],
      scrollIntoView: true,
    }),
  );
  return true;
};

/**
 * Forward-Delete mirror of the Backspace guard: at the end of a line right
 * before a hidden block whose first line starts at the next line (hint
 * callouts, comment chips, example banners), reveal the block instead of
 * letting deleteCharForward silently merge its hidden first line up.
 * (Hidden `\begin`/`\end` marker zones start at this caret position itself,
 * so they are already touch-revealed here and need no guard.)
 */
export const guardDeleteBeforeHiddenBlock: StateCommand = ({
  state,
  dispatch,
}) => {
  if (state.readOnly) return false;
  const range = state.selection.main;
  if (state.selection.ranges.length !== 1 || !range.empty) return false;
  const pos = range.head;
  if (pos !== state.doc.lineAt(pos).to || pos >= state.doc.length) return false;
  const zone = blockZones(state).find(
    (z) =>
      (z.kind === "hint" || z.kind === "comments" || z.kind === "banner") &&
      z.from === pos + 1,
  );
  if (!zone) return false;
  dispatch(
    state.update({
      selection: { anchor: zone.from },
      scrollIntoView: true,
    }),
  );
  return true;
};
