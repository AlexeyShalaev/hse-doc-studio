import { type EditorState } from "@codemirror/state";
import type { EditorStats } from "./types";

// A "word" is a run of letters/digits (Unicode-aware), so LaTeX braces and
// punctuation don't inflate the count. Good enough for thesis length tracking.
const WORD_RE = /[\p{L}\p{N}][\p{L}\p{N}'-]*/gu;

const countWords = (text: string): number => {
  const matches = text.match(WORD_RE);
  return matches ? matches.length : 0;
};

export type DocTotals = { chars: number; words: number };

export const computeStats = (
  state: EditorState,
  /** Totals from a previous call with the same document — skips the full
   *  re-count on pure caret movement (word counting is O(doc)). */
  cachedTotals?: DocTotals | null,
): EditorStats => {
  const totals =
    cachedTotals ??
    ((): DocTotals => {
      const text = state.doc.toString();
      return { chars: text.length, words: countWords(text) };
    })();
  const range = state.selection.main;
  const caretLine = state.doc.lineAt(range.head);
  const selected = range.empty ? "" : state.sliceDoc(range.from, range.to);
  return {
    chars: totals.chars,
    words: totals.words,
    line: caretLine.number,
    column: range.head - caretLine.from + 1,
    selectedChars: range.to - range.from,
    selectedWords: selected ? countWords(selected) : 0,
  };
};
