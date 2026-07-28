import { foldService } from "@codemirror/language";
import { EditorSelection, type StateCommand } from "@codemirror/state";

/**
 * Wrap each selection range in `before … after`. With an empty selection the
 * caret lands between the two so the user can type immediately; with a
 * selection the wrapped text stays selected so the action can be repeated or
 * undone cleanly. Used for ⌘B/⌘I and "wrap in environment".
 */
export const wrapSelection =
  (before: string, after: string): StateCommand =>
  ({ state, dispatch }) => {
    const changes = state.changeByRange((range) => {
      const selected = state.sliceDoc(range.from, range.to);
      const anchor = range.from + before.length;
      const head = anchor + selected.length;
      return {
        changes: {
          from: range.from,
          to: range.to,
          insert: before + selected + after,
        },
        range: EditorSelection.range(anchor, head),
      };
    });
    dispatch(
      state.update(changes, { scrollIntoView: true, userEvent: "input.wrap" }),
    );
    return true;
  };

/** Wrap the selection in a named LaTeX environment on its own lines. */
export const wrapInEnvironment = (envName: string): StateCommand =>
  wrapSelection(`\\begin{${envName}}\n`, `\n\\end{${envName}}`);

const SECTION_LEVELS = [
  "part",
  "chapter",
  "section",
  "subsection",
  "subsubsection",
];
const SECTION_RE = /^\s*\\(part|chapter|section|subsection|subsubsection)\b/;

/**
 * Code folding for LaTeX sectioning commands: a `\section` folds down to (but
 * not including) the next heading of the same or higher level. Complements the
 * environment folding the language pack already provides, so a whole chapter
 * can be collapsed from the fold gutter.
 */
export const sectionFoldService = foldService.of((state, lineStart) => {
  const line = state.doc.lineAt(lineStart);
  const match = SECTION_RE.exec(line.text);
  if (!match?.[1]) return null;
  const level = SECTION_LEVELS.indexOf(match[1]);

  for (let n = line.number + 1; n <= state.doc.lines; n++) {
    const next = state.doc.line(n);
    const nextMatch = SECTION_RE.exec(next.text);
    if (nextMatch?.[1] && SECTION_LEVELS.indexOf(nextMatch[1]) <= level) {
      return { from: line.to, to: state.doc.line(n - 1).to };
    }
  }
  const last = state.doc.line(state.doc.lines);
  return last.number > line.number ? { from: line.to, to: last.to } : null;
});
