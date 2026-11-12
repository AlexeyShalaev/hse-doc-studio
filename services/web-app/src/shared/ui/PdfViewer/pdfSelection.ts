import type { PdfRectPt } from "./pdfText";

/** Выделение в превью: текст, страница его начала и прямоугольники на ней в пунктах PDF. */
export type PdfSelection = { text: string; page: number; rects: PdfRectPt[] };

const RECTS_MAX = 64;

/**
 * Страница и прямоугольники выделения в пунктах PDF от левого верхнего угла.
 * Выделение через несколько страниц: берутся прямоугольники первой (по ней сервер
 * ищет исходник), текст остаётся целиком. null, если выделение вне страниц.
 */
export const selectionGeometry = (
  range: Range,
  container: HTMLElement,
  scale: number,
): { page: number; rects: PdfRectPt[] } | null => {
  const pages = Array.from(
    container.querySelectorAll<HTMLElement>("[data-page]"),
  ).map((el) => ({
    num: Number(el.dataset.page),
    box: el.getBoundingClientRect(),
  }));
  let page: { num: number; box: DOMRect } | null = null;
  const rects: PdfRectPt[] = [];
  for (const r of Array.from(range.getClientRects())) {
    if (r.width < 1 || r.height < 1) continue;
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const host = pages.find(
      (p) =>
        cx >= p.box.left &&
        cx <= p.box.right &&
        cy >= p.box.top &&
        cy <= p.box.bottom,
    );
    if (!host) continue;
    page ??= host;
    if (host.num !== page.num) continue;
    rects.push({
      x: (r.left - host.box.left) / scale,
      y: (r.top - host.box.top) / scale,
      width: r.width / scale,
      height: r.height / scale,
    });
  }
  if (!page || rects.length === 0) return null;
  rects.sort((a, b) => a.y - b.y || a.x - b.x);
  // Соседние куски одной строки (спаны текстового слоя) сливаются в один прямоугольник.
  const merged: PdfRectPt[] = [];
  for (const r of rects) {
    const last = merged.at(-1);
    if (last && Math.abs(last.y - r.y) < 2 && r.x <= last.x + last.width + 3) {
      const right = Math.max(last.x + last.width, r.x + r.width);
      last.width = right - last.x;
      last.height = Math.max(last.height, r.height);
    } else {
      merged.push({ ...r });
    }
  }
  return { page: page.num, rects: merged.slice(0, RECTS_MAX) };
};
