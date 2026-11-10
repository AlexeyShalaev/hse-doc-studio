// Подпись слота внутри пустой рамки на превью PDF. Рамку тянут до любой ширины, и подпись обязана
// уместиться: перенос по словам, затем мельче шрифт, затем многоточие. Строки не наезжают друг на
// друга при любой ширине и высоте рамки.

/** Межстрочный интервал подписи: задан явно, а не наследуется от страницы. */
export const FRAME_LABEL_LINE_HEIGHT = 1.15;
/** Внутренний отступ подписи от рамки, px. */
export const FRAME_LABEL_PAD_PX = 2;

const MAX_FONT_PX = 10;
const MIN_FONT_PX = 6;
const STEP_PX = 0.5;
/** Ширина знака моноширинного шрифта в долях кегля (с запасом). */
const CHAR_EM = 0.62;

/** Сколько строк займёт текст при `perLine` знаках в строке: перенос по словам, длинное слово рвётся. */
const linesNeeded = (words: readonly string[], perLine: number): number => {
  let lines = 0;
  let used = 0;
  for (const word of words) {
    if (used > 0 && used + 1 + word.length <= perLine) {
      used += 1 + word.length;
      continue;
    }
    lines += Math.ceil(word.length / perLine);
    used = word.length % perLine || perLine;
  }
  return Math.max(1, lines);
};

export type FrameLabelFit = {
  fontPx: number;
  /** Сколько строк показать; что не влезло, обрезается многоточием. */
  lines: number;
};

/** Кегль и число строк подписи для рамки `widthPx` × `heightPx`. */
export const fitFrameLabel = (
  label: string,
  widthPx: number,
  heightPx: number,
): FrameLabelFit => {
  const words = label.trim().split(/\s+/).filter(Boolean);
  const width = Math.max(1, widthPx - 2 * FRAME_LABEL_PAD_PX);
  const height = Math.max(1, heightPx - 2 * FRAME_LABEL_PAD_PX);
  const fits = (font: number) => Math.floor(height / (font * FRAME_LABEL_LINE_HEIGHT));
  for (let font = MAX_FONT_PX; font >= MIN_FONT_PX; font -= STEP_PX) {
    const perLine = Math.max(1, Math.floor(width / (font * CHAR_EM)));
    const longest = Math.max(0, ...words.map((w) => w.length));
    const need = linesNeeded(words, perLine);
    if (longest <= perLine && need <= fits(font))
      return { fontPx: font, lines: need };
  }
  return { fontPx: MIN_FONT_PX, lines: Math.max(1, fits(MIN_FONT_PX)) };
};
