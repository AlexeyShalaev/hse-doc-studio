import type * as pdfjsLib from "pdfjs-dist";

// Где на странице PDF стоит текст: для меток комментариев превью. Сравнение то же,
// что у сервера при поиске выделения в исходнике (core/review/pdf_match.py):
// NFKD без диакритики, без регистра, только буквы и цифры. Так переносы,
// лигатуры, кавычки и лишние пробелы текстового слоя не мешают.

/** Прямоугольник на странице в пунктах PDF от левого верхнего угла. */
export type PdfRectPt = { x: number; y: number; width: number; height: number };

/** Кусок текстового слоя страницы в пунктах от левого верхнего угла. */
export type PageTextItem = {
  str: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

const RECTS_MAX = 64;
const MIN_NEEDLE = 4;
const ALNUM = /[\p{L}\p{N}]/u;
const MARKS = /\p{M}/gu;

/** Буквы и цифры строки без диакритики и регистра. */
export const foldText = (text: string): string => {
  let out = "";
  for (const ch of text) {
    for (const part of ch.normalize("NFKD").replace(MARKS, "").toLowerCase())
      if (ALNUM.test(part)) out += part;
  }
  return out;
};

type FoldedPage = { text: string; item: number[]; char: number[] };

const foldItems = (items: PageTextItem[]): FoldedPage => {
  let text = "";
  const item: number[] = [];
  const char: number[] = [];
  items.forEach((it, i) => {
    let j = 0;
    for (const ch of it.str) {
      for (const part of ch.normalize("NFKD").replace(MARKS, "").toLowerCase())
        if (ALNUM.test(part)) {
          text += part;
          item.push(i);
          char.push(j);
        }
      j += ch.length;
    }
  });
  return { text, item, char };
};

const occurrences = (hay: string, needle: string): number[] => {
  const found: number[] = [];
  let at = hay.indexOf(needle);
  while (at !== -1 && found.length < 200) {
    found.push(at);
    at = hay.indexOf(needle, at + 1);
  }
  return found;
};

const mergeLines = (rects: PdfRectPt[]): PdfRectPt[] => {
  const out: PdfRectPt[] = [];
  for (const r of rects) {
    const last = out.at(-1);
    if (
      last &&
      Math.abs(last.y - r.y) < 1.5 &&
      r.x <= last.x + last.width + 4
    ) {
      const right = Math.max(last.x + last.width, r.x + r.width);
      last.x = Math.min(last.x, r.x);
      last.width = right - last.x;
      last.height = Math.max(last.height, r.height);
    } else {
      out.push({ ...r });
    }
  }
  return out.slice(0, RECTS_MAX);
};

/**
 * Прямоугольники текста `needle` на странице или null. Из нескольких вхождений
 * берётся ближайшее к `hintY` (пункты от верха), без подсказки первое.
 */
export const locateText = (
  items: PageTextItem[],
  needle: string,
  hintY?: number,
): PdfRectPt[] | null => {
  const want = foldText(needle);
  if (want.length < MIN_NEEDLE) return null;
  const page = foldItems(items);
  const found = occurrences(page.text, want);
  if (found.length === 0) return null;
  const yOf = (at: number): number => items[page.item[at] ?? 0]?.y ?? 0;
  const best =
    hintY === undefined
      ? (found[0] ?? 0)
      : found.reduce((a, b) =>
          Math.abs(yOf(b) - hintY) < Math.abs(yOf(a) - hintY) ? b : a,
        );
  const last = best + want.length - 1;
  const firstItem = page.item[best] ?? 0;
  const lastItem = page.item[last] ?? firstItem;
  const rects: PdfRectPt[] = [];
  for (let i = firstItem; i <= lastItem; i++) {
    const it = items[i];
    if (!it || it.width <= 0 || it.str.length === 0) continue;
    const from = i === firstItem ? (page.char[best] ?? 0) : 0;
    const to = i === lastItem ? (page.char[last] ?? 0) + 1 : it.str.length;
    const perChar = it.width / it.str.length;
    rects.push({
      x: it.x + perChar * from,
      y: it.y,
      width: Math.max(1, perChar * (to - from)),
      height: it.height,
    });
  }
  return rects.length > 0 ? mergeLines(rects) : null;
};

/** Текстовый слой страницы в пунктах от левого верхнего угла. */
export const pageTextItems = async (
  page: pdfjsLib.PDFPageProxy,
): Promise<PageTextItem[]> => {
  const viewport = page.getViewport({ scale: 1 });
  const content = await page.getTextContent();
  const out: PageTextItem[] = [];
  for (const it of content.items) {
    if (!("str" in it) || it.str.length === 0) continue;
    const transform = it.transform as number[];
    const baseline = transform[5] ?? 0;
    const size = it.height || Math.abs(transform[3] ?? 0) || 10;
    out.push({
      str: it.str,
      x: transform[4] ?? 0,
      // Верх строки чуть выше кегля над базовой линией, низ с выносными.
      y: viewport.height - baseline - size * 0.9,
      width: it.width,
      height: size * 1.15,
    });
  }
  return out;
};
