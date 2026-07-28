import { syntaxTree } from "@codemirror/language";
import type { EditorState, StateCommand } from "@codemirror/state";
import type { SyntaxNode } from "@lezer/common";

/**
 * Word-processor list ergonomics for the visual mode:
 *  - Enter inside a list starts a new `\item` (keeping the indent);
 *  - Enter on an empty item deletes it and exits below the list;
 *  - Backspace right after an `\item ` prefix merges into the previous item.
 * Every command falls through (returns false) outside these exact spots so
 * the default keymap keeps working.
 */

const ITEM_PREFIX_RE = /^(\s*)\\item(\[[^\]]*\])?( ?)/;
const EMPTY_ITEM_RE = /^\s*\\item(\[[^\]]*\])?\s*$/;

const enclosingListAt = (
  state: EditorState,
  pos: number,
): SyntaxNode | null => {
  let node: SyntaxNode | null = syntaxTree(state).resolveInner(pos, -1);
  for (; node; node = node.parent) {
    if (node.name === "ListEnvironment") break;
  }
  if (!node) return null;
  // Only positions inside the list body count — not the begin/end markers.
  const begin = node.getChild("BeginEnv");
  const end = node.getChild("EndEnv");
  if (!begin || !end) return null;
  return pos > begin.to && pos <= end.from ? node : null;
};

export const insertListItem: StateCommand = ({ state, dispatch }) => {
  if (state.readOnly) return false;
  const range = state.selection.main;
  if (state.selection.ranges.length !== 1 || !range.empty) return false;
  const pos = range.head;
  const list = enclosingListAt(state, pos);
  if (!list) return false;
  const line = state.doc.lineAt(pos);

  if (EMPTY_ITEM_RE.test(line.text) && pos >= line.to) {
    // Empty item + Enter → drop the item and step out below the list.
    const end = list.getChild("EndEnv");
    if (!end) return false;
    const endLine = state.doc.lineAt(end.to);
    const changes = state.changes([
      { from: line.from, to: Math.min(line.to + 1, state.doc.length) },
      { from: endLine.to, insert: "\n" },
    ]);
    dispatch(
      state.update({
        changes,
        selection: { anchor: changes.mapPos(endLine.to, 1) },
        scrollIntoView: true,
        userEvent: "delete",
      }),
    );
    return true;
  }

  const indent = /^\s*/.exec(line.text)?.[0] ?? "";
  const insert = `\n${indent}\\item `;
  dispatch(
    state.update({
      changes: { from: pos, to: pos, insert },
      selection: { anchor: pos + insert.length },
      scrollIntoView: true,
      userEvent: "input",
    }),
  );
  return true;
};

export const mergeListItemBackwards: StateCommand = ({ state, dispatch }) => {
  if (state.readOnly) return false;
  const range = state.selection.main;
  if (state.selection.ranges.length !== 1 || !range.empty) return false;
  const pos = range.head;
  const line = state.doc.lineAt(pos);
  if (line.from === 0) return false;
  const match = ITEM_PREFIX_RE.exec(line.text);
  if (!match || pos !== line.from + match[0].length) return false;
  const list = enclosingListAt(state, pos);
  if (!list) return false;

  // Merging the first item would splice its text into the `\begin{…}` line.
  const begin = list.getChild("BeginEnv");
  if (begin && state.doc.lineAt(begin.from).number === line.number - 1) {
    return false;
  }

  dispatch(
    state.update({
      changes: { from: line.from - 1, to: line.from + match[0].length },
      selection: { anchor: line.from - 1 },
      scrollIntoView: true,
      userEvent: "delete",
    }),
  );
  return true;
};
