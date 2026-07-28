import { syntaxTree } from "@codemirror/language";
import {
  EditorSelection,
  type EditorState,
  type StateCommand,
} from "@codemirror/state";
import { visualConfigFacet } from "./config";

/**
 * Word-style template-field navigation. A "field" is an unfilled spot the
 * student must replace with real text: an `\hseFill{hint}` placeholder, or a
 * zero-argument meta macro whose stored value is empty / itself an
 * `\hseFill{…}` default. Tab/Shift+Tab cycle through them with the whole
 * macro selected, so the first keystroke replaces it — exactly like tabbing
 * through content controls in Word.
 */

export type FillField = { from: number; to: number };

const isUnfilledExpansion = (value: string | undefined): boolean =>
  value !== undefined && (value === "" || value.startsWith("\\hseFill{"));

// Fields only change with the parse tree or the macro table — memoize per
// identity pair so caret movement / Tab presses cost O(1), not a tree walk.
let lastTree: unknown = null;
let lastMacros: Record<string, string> | null = null;
let lastFields: FillField[] = [];

/** All unfilled fields in document order. Pure; exported for tests/stats. */
export const collectFillFields = (state: EditorState): FillField[] => {
  const tree = syntaxTree(state);
  const macros = state.facet(visualConfigFacet).macros;
  if (tree === lastTree && macros === lastMacros) return lastFields;
  const fields: FillField[] = [];
  tree.iterate({
    enter: (node) => {
      if (node.name !== "UnknownCommand") return undefined;
      const ctrl = node.node.getChild("CtrlSeq");
      if (!ctrl) return undefined;
      const command = state.doc.sliceString(ctrl.from, ctrl.to);
      if (command === "\\hseFill") {
        // Select the whole macro incl. its {hint} argument.
        fields.push({ from: node.from, to: node.to });
        return false;
      }
      if (
        !node.node.getChild("TextArgument") &&
        isUnfilledExpansion(macros[command.slice(1)])
      ) {
        // Empty meta macro — select just the control word.
        fields.push({ from: ctrl.from, to: ctrl.to });
        return false;
      }
      return undefined;
    },
  });
  lastTree = tree;
  lastMacros = macros;
  lastFields = fields;
  return fields;
};

const selectField = (
  target: FillField,
  { state, dispatch }: Parameters<StateCommand>[0],
): boolean => {
  dispatch(
    state.update({
      selection: EditorSelection.range(target.from, target.to),
      scrollIntoView: true,
      userEvent: "select",
    }),
  );
  return true;
};

/** Jump to the next unfilled field (wraps). Falls through when none exist. */
export const nextField: StateCommand = (target) => {
  const fields = collectFillFields(target.state);
  if (fields.length === 0) return false;
  const pos = target.state.selection.main.to;
  const found = fields.find((f) => f.from >= pos) ?? fields[0];
  if (!found) return false;
  return selectField(found, target);
};

/** Jump to the previous unfilled field (wraps). */
export const prevField: StateCommand = (target) => {
  const fields = collectFillFields(target.state);
  if (fields.length === 0) return false;
  const pos = target.state.selection.main.from;
  const found =
    [...fields].reverse().find((f) => f.to <= pos) ?? fields[fields.length - 1];
  if (!found) return false;
  return selectField(found, target);
};
