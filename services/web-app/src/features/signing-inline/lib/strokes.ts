// Нарисованная подпись: штрихи в координатах холста (CSS px) и их растр в PNG без фона.

export type StrokePoint = { x: number; y: number };
export type Stroke = StrokePoint[];

/** Цвет чернил: тёмно-синий, как у ручки; читается на белом листе. */
export const INK_COLOR = "#0a1e78";
export const INK_WIDTH = 2.4;

/** Рисует штрихи сглаженной линией: точки соединяются через середины отрезков. */
export const paintStrokes = (
  g: CanvasRenderingContext2D,
  strokes: readonly Stroke[],
  width: number,
): void => {
  g.strokeStyle = INK_COLOR;
  g.fillStyle = INK_COLOR;
  g.lineWidth = width;
  g.lineCap = "round";
  g.lineJoin = "round";
  for (const stroke of strokes) {
    const first = stroke[0];
    if (!first) continue;
    if (stroke.length === 1) {
      g.beginPath();
      g.arc(first.x, first.y, width / 2, 0, Math.PI * 2);
      g.fill();
      continue;
    }
    g.beginPath();
    g.moveTo(first.x, first.y);
    for (let i = 1; i < stroke.length - 1; i++) {
      const a = stroke[i];
      const b = stroke[i + 1];
      if (!a || !b) continue;
      g.quadraticCurveTo(a.x, a.y, (a.x + b.x) / 2, (a.y + b.y) / 2);
    }
    const last = stroke[stroke.length - 1];
    if (last) g.lineTo(last.x, last.y);
    g.stroke();
  }
};

const PADDING = 6;
/** Растр крупнее экрана: подпись в PDF не должна рассыпаться на пиксели. */
const SCALE = 3;

/** Рамка вокруг чернил; null, если ничего не нарисовано. */
export const strokesBounds = (
  strokes: readonly Stroke[],
): { x: number; y: number; width: number; height: number } | null => {
  const points = strokes.flat();
  if (points.length === 0) return null;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x = Math.min(...xs) - PADDING;
  const y = Math.min(...ys) - PADDING;
  return {
    x,
    y,
    width: Math.max(...xs) + PADDING - x,
    height: Math.max(...ys) + PADDING - y,
  };
};

/** PNG с прозрачным фоном, обрезанный по чернилам. */
export const strokesToPng = (strokes: readonly Stroke[]): Promise<Blob> =>
  new Promise((resolve, reject) => {
    const bounds = strokesBounds(strokes);
    if (!bounds) {
      reject(new Error("nothing drawn"));
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(bounds.width * SCALE);
    canvas.height = Math.ceil(bounds.height * SCALE);
    const g = canvas.getContext("2d");
    if (!g) {
      reject(new Error("canvas is not available"));
      return;
    }
    g.scale(SCALE, SCALE);
    g.translate(-bounds.x, -bounds.y);
    paintStrokes(g, strokes, INK_WIDTH);
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("canvas export failed"));
    }, "image/png");
  });
