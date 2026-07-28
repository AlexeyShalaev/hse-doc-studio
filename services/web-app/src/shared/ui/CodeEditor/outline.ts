import { syntaxTree } from "@codemirror/language";
import type { EditorState } from "@codemirror/state";
import { HEADING_LEVELS } from "./visual/nodeSets";
import type { OutlineItem } from "./types";

/**
 * Document outline (headings) for the Word-style navigation pane. Built from
 * the syntax tree and memoized per tree identity, so selection changes and
 * repeated reads cost O(1).
 */

/** Make a heading title readable: ⟨hint⟩ for \hseFill, strip other markup. */
const cleanTitle = (raw: string): string =>
  raw
    .replace(/\\hseFill\{([^}]*)\}/g, "⟨$1⟩")
    .replace(/\\[a-zA-Z@]+\*?\s*/g, "")
    .replace(/[{}]/g, "")
    .replace(/\s+/g, " ")
    .trim();

let lastTree: unknown = null;
let lastItems: OutlineItem[] = [];

export const computeOutline = (state: EditorState): OutlineItem[] => {
  const tree = syntaxTree(state);
  if (tree === lastTree) return lastItems;
  const items: OutlineItem[] = [];
  const doc = state.doc;
  tree.iterate({
    enter: (node) => {
      if (node.name !== "SectioningCommand") return undefined;
      const parentName = node.node.parent?.name ?? "";
      const level = HEADING_LEVELS[parentName] ?? 2;
      const body = node.node
        .getChild("SectioningArgument")
        ?.getChild("LongArg");
      const title = body ? cleanTitle(doc.sliceString(body.from, body.to)) : "";
      items.push({
        level,
        title: title || "—",
        line: doc.lineAt(node.from).number,
        from: node.from,
      });
      return false;
    },
  });
  lastTree = tree;
  lastItems = items;
  return items;
};

/** Index of the heading whose section contains `pos` (-1 before the first). */
export const outlineActiveIndex = (
  items: OutlineItem[],
  pos: number,
): number => {
  let active = -1;
  for (let i = 0; i < items.length; i += 1) {
    const item = items[i];
    if (item && item.from <= pos) active = i;
    else break;
  }
  return active;
};
