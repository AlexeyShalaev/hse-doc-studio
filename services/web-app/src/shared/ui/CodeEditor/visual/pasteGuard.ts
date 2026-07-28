import { syntaxTree } from "@codemirror/language";
import { EditorSelection, type Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import type { SyntaxNode } from "@lezer/common";

/**
 * Safe paste for the visual mode: plain prose pasted from Word/браузера gets
 * its LaTeX special characters escaped (a bare «100% готово» would otherwise
 * comment out the rest of the line). Text that already looks like LaTeX is
 * left untouched, as are pastes into math/verbatim/comments/preamble.
 * Ctrl/Cmd+Shift+V pastes raw. One transaction → one Ctrl+Z undoes it.
 */

const LATEX_MARKER_RE = /\\[a-zA-Z]+|\$[^\n$]+\$/;
const SPECIALS_RE = /[\\%&#_^~$]/;

const ESCAPES: Record<string, string> = {
  "\\": "\\textbackslash{}",
  "%": "\\%",
  "&": "\\&",
  "#": "\\#",
  _: "\\_",
  "^": "\\textasciicircum{}",
  "~": "\\textasciitilde{}",
  $: "\\$",
};

/** Escape LaTeX specials in plain prose (mirrors the backend's texesc). */
export const escapeLatexText = (text: string): string =>
  text.replace(/[\\%&#_^~$]/g, (ch) => ESCAPES[ch] ?? ch);

/** Should this clipboard text be escaped? Pure; exported for tests. */
export const shouldEscapePaste = (text: string): boolean =>
  text.length > 0 && SPECIALS_RE.test(text) && !LATEX_MARKER_RE.test(text);

const PROTECTED_NODES = new Set([
  "Comment",
  "Math",
  "InlineMath",
  "DisplayMath",
  "DollarMath",
  "BracketMath",
  "ParenMath",
  "EquationEnvironment",
  "EquationArrayEnvironment",
  "VerbatimEnvironment",
  "ListingEnvironment",
  "LiteralArgContent",
  "UrlArgument",
  "FilePathArgument",
  // Identifier arguments (\cite/\ref/\label keys, package/class names) —
  // escaping a pasted Zotero key like ivanov_vkr_2024 would break it.
  "ShortTextArgument",
]);

const inProtectedContext = (view: EditorView, pos: number): boolean => {
  let node: SyntaxNode | null = syntaxTree(view.state).resolveInner(pos, -1);
  for (; node; node = node.parent) {
    if (PROTECTED_NODES.has(node.name)) return true;
  }
  // The preamble is setup code, not prose.
  let preambleEnd = -1;
  syntaxTree(view.state).iterate({
    enter: (node) => {
      if (preambleEnd >= 0) return false;
      if (node.name === "DocumentEnvironment") {
        const begin = node.node.getChild("BeginEnv");
        if (begin) preambleEnd = begin.to;
        return false;
      }
      return undefined;
    },
  });
  return preambleEnd >= 0 && pos < preambleEnd;
};

export const pasteGuard = (onPasteTransformed?: () => void): Extension => {
  // Ctrl/Cmd+Shift+V fires a native paste right after this keydown — treat
  // the next paste event within this window as "raw, do not touch".
  let rawPasteUntil = 0;
  return EditorView.domEventHandlers({
    keydown: (event) => {
      if (
        // event.code is layout-independent — with a Cyrillic layout the
        // physical V key reports key "м", which must still trigger raw paste.
        (event.code === "KeyV" || event.key.toLowerCase() === "v") &&
        (event.ctrlKey || event.metaKey) &&
        event.shiftKey
      ) {
        rawPasteUntil = Date.now() + 300;
      }
      return false;
    },
    paste: (event, view) => {
      if (view.state.readOnly) return false;
      if (Date.now() < rawPasteUntil) return false;
      const text = event.clipboardData?.getData("text/plain");
      if (!text || !shouldEscapePaste(text)) return false;
      // Decide per selection range (multi-cursor): escape in prose, keep raw
      // in protected contexts. One transaction → one Ctrl+Z.
      const needsEscape = view.state.selection.ranges.map(
        (r) => !inProtectedContext(view, r.head),
      );
      if (!needsEscape.some(Boolean)) return false;
      event.preventDefault();
      const escaped = escapeLatexText(text);
      let index = 0;
      view.dispatch(
        view.state.changeByRange((range) => {
          const insert = needsEscape[index] ? escaped : text;
          index += 1;
          return {
            changes: { from: range.from, to: range.to, insert },
            range: EditorSelection.cursor(range.from + insert.length),
          };
        }),
        { userEvent: "input.paste", scrollIntoView: true },
      );
      onPasteTransformed?.();
      return true;
    },
  });
};
