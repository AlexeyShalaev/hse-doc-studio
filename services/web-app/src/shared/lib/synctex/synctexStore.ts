import { create } from "zustand";

// A pending forward jump (source -> PDF): scroll the preview to this box and
// flash it. `token` makes repeat jumps to the same spot re-fire the effect.
export type PdfJump = {
  page: number;
  xPt: number;
  yPt: number;
  widthPt: number;
  heightPt: number;
  token: number;
};

// A pending inverse jump (PDF -> source): open the editor at this file + line.
export type SourceJump = {
  file: string;
  line: number;
  column: number;
  token: number;
};

// A pending "find this PDF text in the source" request (free-text search).
export type SourceFind = {
  text: string;
  token: number;
};

type SyncTexState = {
  pdfJump: PdfJump | null;
  sourceJump: SourceJump | null;
  sourceFind: SourceFind | null;
  requestPdfJump: (j: Omit<PdfJump, "token">) => void;
  requestSourceJump: (j: Omit<SourceJump, "token">) => void;
  requestSourceFind: (text: string) => void;
};

// Monotonic tokens (no Date.now/Math.random needed) so each request is distinct.
let pdfToken = 0;
let sourceToken = 0;
let findToken = 0;

/**
 * Cross-pane SyncTeX channel. The source editor and the PDF preview live in
 * separate tabs; this store is how a click in one asks the other to navigate
 * (and DocumentTabs to switch tabs). Mirrors the workspaceStore askAgent pattern.
 */
export const useSyncTexStore = create<SyncTexState>((set) => ({
  pdfJump: null,
  sourceJump: null,
  sourceFind: null,
  requestPdfJump: (j) => {
    pdfToken += 1;
    set({ pdfJump: { ...j, token: pdfToken } });
  },
  requestSourceJump: (j) => {
    sourceToken += 1;
    set({ sourceJump: { ...j, token: sourceToken } });
  },
  requestSourceFind: (text) => {
    findToken += 1;
    set({ sourceFind: { text, token: findToken } });
  },
}));
