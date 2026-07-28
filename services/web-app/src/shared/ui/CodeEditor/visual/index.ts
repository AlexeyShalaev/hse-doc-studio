import { Prec, type Extension } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import {
  atomicBlocksField,
  preambleCollapsedField,
  protectEmbeddedInputs,
} from "./atomicBlocks";
import {
  guardBackspaceAfterHiddenBlock,
  guardDeleteBeforeHiddenBlock,
  insertParagraphAfterHeading,
  smartEnd,
  smartHome,
} from "./caretInput";
import {
  visualConfigFacet,
  visualCallbacksFacet,
  type VisualCallbacks,
  type VisualConfig,
} from "./config";
import { nextField, prevField } from "./fieldNav";
import { imageInsert } from "./imageInsert";
import { visualViewPlugin } from "./inlineDecorations";
import { insertListItem, mergeListItemBackwards } from "./listInput";
import { pasteGuard } from "./pasteGuard";
import { selectionToolbarExtension } from "./selectionToolbar";
import { slashMenuExtension } from "./slashMenu";
import { visualTheme } from "./visualTheme";

export type { VisualConfig } from "./config";

export type { VisualCallbacks } from "./config";

/**
 * The Overleaf-style visual editing bundle: same document text, LaTeX markup
 * hidden/styled via decorations, revealed around the selection. Composed into
 * the editor through `visualCompartment` (see cmExtensions.ts) so toggling
 * preserves undo history, scroll position and selection.
 */
export const visualLatexExtension = (
  config?: Partial<VisualConfig>,
  callbacks?: VisualCallbacks,
): Extension => [
  visualConfigFacet.of({
    macros: config?.macros ?? {},
    showComments: config?.showComments ?? false,
    hintPrefixes: config?.hintPrefixes ?? [],
    highlightEnvs: config?.highlightEnvs ?? [],
    headingAlignments: config?.headingAlignments ?? {},
    embeddedInputBasenames: config?.embeddedInputBasenames ?? [],
    embeddedInputKinds: config?.embeddedInputKinds ?? {},
    embeddedInputSources: config?.embeddedInputSources ?? {},
  }),
  visualCallbacksFacet.of(callbacks ?? {}),
  // A Word-like page always wraps at the paper edge.
  EditorView.lineWrapping,
  preambleCollapsedField,
  atomicBlocksField,
  protectEmbeddedInputs,
  visualViewPlugin(callbacks),
  selectionToolbarExtension,
  visualTheme,
  slashMenuExtension,
  // Image insertion runs before the text paste-guard: an image paste has no
  // text payload, so ordering only matters for mixed clipboards.
  imageInsert(callbacks?.onDropImage, callbacks?.onImageInsertSkipped),
  pasteGuard(callbacks?.onPasteTransformed),
  Prec.high(
    keymap.of([
      { key: "Enter", run: insertParagraphAfterHeading },
      { key: "Enter", run: insertListItem },
      { key: "Backspace", run: guardBackspaceAfterHiddenBlock },
      { key: "Backspace", run: mergeListItemBackwards },
      { key: "Delete", run: guardDeleteBeforeHiddenBlock },
      { key: "Tab", run: nextField },
      { key: "Shift-Tab", run: prevField },
      { key: "Home", run: smartHome },
      { key: "End", run: smartEnd },
    ]),
  ),
];
