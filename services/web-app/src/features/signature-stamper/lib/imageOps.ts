// Geometric + manual editing operations for the signature editor, plus image
// input helpers (clipboard / blob). All canvas-based, zero dependencies, never
// mutate their input (except the explicitly in-place eraser).

export const cloneImageData = (d: ImageData): ImageData =>
  new ImageData(new Uint8ClampedArray(d.data), d.width, d.height);

const makeCtx = (w: number, h: number): CanvasRenderingContext2D => {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context unavailable");
  return ctx;
};

/** Decode any image Blob/File the browser supports into ImageData. */
export const blobToImageData = async (blob: Blob): Promise<ImageData> => {
  const bmp = await createImageBitmap(blob);
  const w = bmp.width;
  const h = bmp.height;
  const ctx = makeCtx(w, h);
  ctx.drawImage(bmp, 0, 0);
  bmp.close();
  return ctx.getImageData(0, 0, w, h);
};

/** Read an image from the system clipboard, or null if none / not permitted. */
export const readClipboardImage = async (): Promise<Blob | null> => {
  // `read` is typed as always-present but isn't in every browser/context.
  if (!("read" in navigator.clipboard)) return null;
  try {
    const items = await navigator.clipboard.read();
    for (const item of items) {
      const type = item.types.find((t) => t.startsWith("image/"));
      if (type) return await item.getType(type);
    }
  } catch {
    return null;
  }
  return null;
};

/** Extract the first image File from a paste/drop DataTransfer, or null. */
export const imageFromDataTransfer = (dt: DataTransfer | null): File | null => {
  if (!dt) return null;
  for (const item of dt.items) {
    if (item.kind === "file" && item.type.startsWith("image/")) {
      const f = item.getAsFile();
      if (f) return f;
    }
  }
  for (const f of dt.files) {
    if (f.type.startsWith("image/")) return f;
  }
  return null;
};

export const cropImageData = (
  src: ImageData,
  x: number,
  y: number,
  w: number,
  h: number,
): ImageData => {
  const cx = Math.max(0, Math.round(x));
  const cy = Math.max(0, Math.round(y));
  const cw = Math.min(src.width - cx, Math.round(w));
  const ch = Math.min(src.height - cy, Math.round(h));
  if (cw <= 0 || ch <= 0) return cloneImageData(src);
  const ctx = makeCtx(src.width, src.height);
  ctx.putImageData(src, 0, 0);
  return ctx.getImageData(cx, cy, cw, ch);
};

const luminance = (r: number, g: number, b: number): number =>
  0.299 * r + 0.587 * g + 0.114 * b;

/**
 * Bounding box of "ink" — pixels that are both visible (alpha) and not near
 * white. Works before background removal (dark-on-white) and after (opaque ink
 * on transparency). Returns null for a blank image.
 */
export const contentBounds = (
  src: ImageData,
): { x: number; y: number; w: number; h: number } | null => {
  const { data, width, height } = src;
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = (y * width + x) * 4;
      const a = data[i + 3] ?? 0;
      if (a <= 16) continue;
      const lum = luminance(data[i] ?? 0, data[i + 1] ?? 0, data[i + 2] ?? 0);
      if (lum >= 220) continue;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (maxX < 0) return null;
  return { x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 };
};

/** Crop to the content bounding box plus a small padding. */
export const autoTrim = (src: ImageData, pad = 8): ImageData => {
  const b = contentBounds(src);
  if (!b) return src;
  return cropImageData(src, b.x - pad, b.y - pad, b.w + pad * 2, b.h + pad * 2);
};

export const rotate90 = (src: ImageData, dir: "cw" | "ccw"): ImageData => {
  const { width: w, height: h } = src;
  const from = makeCtx(w, h);
  from.putImageData(src, 0, 0);
  const ctx = makeCtx(h, w); // dimensions swap
  ctx.translate(h / 2, w / 2);
  ctx.rotate(dir === "cw" ? Math.PI / 2 : -Math.PI / 2);
  ctx.drawImage(from.canvas, -w / 2, -h / 2);
  return ctx.getImageData(0, 0, h, w);
};

/**
 * "Magic eraser": erase pixels whose colour matches the one clicked at
 * (sx, sy), within `tolerance` (RGB Euclidean distance). `contiguous` limits
 * the erase to the connected blob touching the click; otherwise every matching
 * pixel anywhere is erased. Returns a new ImageData (input untouched).
 */
export const magicErase = (
  src: ImageData,
  sx: number,
  sy: number,
  tolerance: number,
  contiguous: boolean,
): ImageData => {
  const out = cloneImageData(src);
  const { data, width, height } = out;
  const ix = Math.round(sx);
  const iy = Math.round(sy);
  if (ix < 0 || iy < 0 || ix >= width || iy >= height) return out;

  const seed = (iy * width + ix) * 4;
  const tr = data[seed] ?? 0;
  const tg = data[seed + 1] ?? 0;
  const tb = data[seed + 2] ?? 0;
  if ((data[seed + 3] ?? 0) === 0) return out; // clicked an already-clear pixel

  const tol2 = tolerance * tolerance;
  const matches = (i: number): boolean => {
    if ((data[i + 3] ?? 0) === 0) return false;
    const dr = (data[i] ?? 0) - tr;
    const dg = (data[i + 1] ?? 0) - tg;
    const db = (data[i + 2] ?? 0) - tb;
    return dr * dr + dg * dg + db * db <= tol2;
  };

  if (!contiguous) {
    for (let i = 0; i < data.length; i += 4) {
      if (matches(i)) data[i + 3] = 0;
    }
    return out;
  }

  // 4-connected flood fill from the clicked pixel.
  const visited = new Uint8Array(width * height);
  const start = iy * width + ix;
  const stack: number[] = [start];
  visited[start] = 1;
  while (stack.length > 0) {
    const p = stack.pop();
    if (p === undefined) break;
    if (!matches(p * 4)) continue;
    data[p * 4 + 3] = 0;
    const px = p % width;
    const py = (p / width) | 0;
    if (px > 0 && visited[p - 1] === 0) {
      visited[p - 1] = 1;
      stack.push(p - 1);
    }
    if (px < width - 1 && visited[p + 1] === 0) {
      visited[p + 1] = 1;
      stack.push(p + 1);
    }
    if (py > 0 && visited[p - width] === 0) {
      visited[p - width] = 1;
      stack.push(p - width);
    }
    if (py < height - 1 && visited[p + width] === 0) {
      visited[p + width] = 1;
      stack.push(p + width);
    }
  }
  return out;
};

/** Erase a filled circle (set alpha to 0) directly on `d`. Image-space coords. */
export const eraseCircleInPlace = (
  d: ImageData,
  cx: number,
  cy: number,
  radius: number,
): void => {
  const { data, width, height } = d;
  const r2 = radius * radius;
  const x0 = Math.max(0, Math.floor(cx - radius));
  const x1 = Math.min(width - 1, Math.ceil(cx + radius));
  const y0 = Math.max(0, Math.floor(cy - radius));
  const y1 = Math.min(height - 1, Math.ceil(cy + radius));
  for (let y = y0; y <= y1; y += 1) {
    for (let x = x0; x <= x1; x += 1) {
      const dx = x - cx;
      const dy = y - cy;
      if (dx * dx + dy * dy <= r2) {
        data[(y * width + x) * 4 + 3] = 0;
      }
    }
  }
};
