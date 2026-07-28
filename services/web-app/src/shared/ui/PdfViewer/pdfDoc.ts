import type * as pdfjsLib from "pdfjs-dist";
import type { OutlineEntry } from "./PdfOutline";
import type { PageDim } from "./PdfPage";

// Shared pdf.js document helpers used by both the scrolling reader (PdfViewer)
// and the visual-diff view (PdfDiffView): page dimensions, bookmark outline,
// and a plain text-occurrence counter for in-document search.

type RawOutline = Awaited<ReturnType<pdfjsLib.PDFDocumentProxy["getOutline"]>>;

const resolveDest = async (
  pdf: pdfjsLib.PDFDocumentProxy,
  dest: string | unknown[] | null,
): Promise<number | null> => {
  try {
    const explicit =
      typeof dest === "string" ? await pdf.getDestination(dest) : dest;
    if (!Array.isArray(explicit) || explicit.length === 0) return null;
    const ref = explicit[0] as Parameters<typeof pdf.getPageIndex>[0] | null;
    if (ref == null || typeof ref !== "object") return null;
    const idx = await pdf.getPageIndex(ref);
    return idx + 1;
  } catch {
    return null;
  }
};

const buildOutline = async (
  pdf: pdfjsLib.PDFDocumentProxy,
  raw: RawOutline,
): Promise<OutlineEntry[]> => {
  const out: OutlineEntry[] = [];
  for (const node of raw) {
    const pageNum =
      node.dest != null ? await resolveDest(pdf, node.dest) : null;
    const items =
      node.items.length > 0
        ? await buildOutline(pdf, node.items as RawOutline)
        : [];
    out.push({ title: node.title, pageNum, items });
  }
  return out;
};

/** Resolve a document's bookmark tree to page-numbered entries ([] if none). */
export const getOutlineFor = async (
  doc: pdfjsLib.PDFDocumentProxy,
): Promise<OutlineEntry[]> => {
  const raw = await doc.getOutline().catch(() => null);
  return raw ? buildOutline(doc, raw) : [];
};

/** Natural (scale-1) width/height in points for every page, in order. */
export const loadPageDims = async (
  doc: pdfjsLib.PDFDocumentProxy,
): Promise<PageDim[]> =>
  Promise.all(
    Array.from({ length: doc.numPages }, async (_, i) => {
      const page = await doc.getPage(i + 1);
      const vp = page.getViewport({ scale: 1 });
      return { num: i + 1, widthPt: vp.width, heightPt: vp.height };
    }),
  );

/** Count non-overlapping occurrences of `needle` in `haystack`. */
export const countOccurrences = (haystack: string, needle: string): number => {
  if (!needle) return 0;
  let count = 0;
  let from = 0;
  for (;;) {
    const idx = haystack.indexOf(needle, from);
    if (idx === -1) break;
    count += 1;
    from = idx + needle.length;
  }
  return count;
};
