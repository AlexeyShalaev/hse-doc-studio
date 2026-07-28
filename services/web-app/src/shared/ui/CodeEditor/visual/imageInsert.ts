import { StateEffect, StateField, type Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { preambleEndAt } from "./widgets";

/**
 * Word-style image insertion: paste a screenshot (or drop an image file)
 * into the visual editor → the host uploads it into the project and a ready
 * `figure` block is inserted, its caption an `\hseFill{…}` field selected
 * for immediate typing. The document changes only AFTER a successful upload;
 * the insertion point is captured at gesture time and mapped through any
 * edits made while the upload was in flight.
 */

const CAPTION_FILL = "\\hseFill{подпись рисунка}";

// LaTeX (xelatex + graphicx) compiles only these — a .webp/.gif figure
// would preview fine in the editor and then break the build.
const SUPPORTED_IMAGE_MIME = new Set(["image/png", "image/jpeg", "image/bmp"]);

/** Figure snippet for an uploaded image (path relative to the doc dir). */
export const buildFigureTemplate = (path: string): string => {
  const stem = (path.split("/").pop() ?? "img")
    .replace(/\.[^.]+$/, "")
    .replace(/[^a-zA-Z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  return [
    "\\begin{figure}[h]",
    "\t\\centering",
    `\t\\includegraphics[width=0.8\\textwidth]{${path}}`,
    `\t\\caption{${CAPTION_FILL}}`,
    `\t\\label{fig:${stem || "img"}}`,
    "\\end{figure}",
  ].join("\n");
};

const pickImage = (transfer: DataTransfer | null): File | null => {
  if (!transfer) return null;
  for (const file of Array.from(transfer.files)) {
    if (SUPPORTED_IMAGE_MIME.has(file.type)) return file;
  }
  return null;
};

/** Insertion point captured at gesture time, mapped through edits. */
const setPendingInsert = StateEffect.define<number | null>();
const pendingInsertField = StateField.define<number | null>({
  create: () => null,
  update: (value, tr) => {
    for (const effect of tr.effects) {
      if (effect.is(setPendingInsert)) return effect.value;
    }
    return value == null ? null : tr.changes.mapPos(value, 1);
  },
});

const insertFigure = (view: EditorView, path: string): void => {
  if (view.state.readOnly) return;
  let head =
    view.state.field(pendingInsertField, false) ??
    view.state.selection.main.head;
  // Never insert into the (possibly collapsed) preamble — a figure before
  // \begin{document} fails the compile invisibly.
  const preambleEnd = preambleEndAt(view);
  if (preambleEnd >= 0 && head < preambleEnd) head = preambleEnd;
  const template = buildFigureTemplate(path);
  const line = view.state.doc.lineAt(head);
  const empty = line.text.trim() === "";
  const insert = empty ? template : `\n${template}`;
  const at = line.to;
  const captionAt = at + insert.indexOf(CAPTION_FILL);
  view.dispatch({
    changes: { from: at, insert: `${insert}\n` },
    // Select the caption placeholder so the user can type it right away
    // (also puts the construct into its revealed, editable state).
    selection: {
      anchor: captionAt,
      head: captionAt + CAPTION_FILL.length,
    },
    effects: setPendingInsert.of(null),
    scrollIntoView: true,
    userEvent: "input.paste",
  });
  view.focus();
};

export const imageInsert = (
  onDropImage?: (file: File) => Promise<string | null>,
  onInsertSkipped?: () => void,
): Extension => {
  if (!onDropImage) return [];
  const upload = (view: EditorView, file: File, gestureAt: number): void => {
    view.dispatch({ effects: setPendingInsert.of(gestureAt) });
    void onDropImage(file).then((path) => {
      if (!path) return;
      if (!view.dom.isConnected) {
        // The user switched files while uploading — the image IS in the
        // project, but there is no live document to insert into.
        onInsertSkipped?.();
        return;
      }
      insertFigure(view, path);
    });
  };
  return [
    pendingInsertField,
    EditorView.domEventHandlers({
      paste: (event, view) => {
        if (view.state.readOnly) return false;
        // Office rich clipboards (Excel/Word) carry a bitmap rendition of
        // the copied content ALONGSIDE the text — a text payload means the
        // user is pasting text, not an image.
        if (event.clipboardData?.getData("text/plain")) return false;
        const file = pickImage(event.clipboardData);
        if (!file) return false;
        event.preventDefault();
        upload(view, file, view.state.selection.main.head);
        return true;
      },
      drop: (event, view) => {
        if (view.state.readOnly) return false;
        const file = pickImage(event.dataTransfer);
        if (!file) return false;
        event.preventDefault();
        const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
        upload(view, file, pos ?? view.state.selection.main.head);
        return true;
      },
    }),
  ];
};
