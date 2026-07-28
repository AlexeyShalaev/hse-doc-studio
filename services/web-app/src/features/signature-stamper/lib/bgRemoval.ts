// Client-side signature background removal.
//
// A signature is the *easy* case of background removal: dark ink on a light
// page. We map per-pixel luminance to alpha — bright (paper) → transparent,
// dark (ink) → opaque — with a soft ramp so anti-aliased strokes keep smooth
// edges. No ML model, no backend round-trip, no extra dependencies; runs on a
// <canvas> in the browser and the result plugs straight into the PNG upload.

import { i18n } from "@shared/lib";

export type BgRemovalOptions = {
  /** Luminance (0..255) midpoint: pixels brighter than this fade to transparent. */
  threshold: number;
  /** Half-width of the alpha ramp around `threshold` (0 = hard edge). */
  softness: number;
  /** Hex colour to recolour the ink to, or null to keep original pixel colours. */
  recolor: string | null;
};

export const DEFAULT_SOFTNESS = 24;

const luminance = (r: number, g: number, b: number): number =>
  0.299 * r + 0.587 * g + 0.114 * b;

/** Load a File into ImageData via an offscreen canvas. */
export const fileToImageData = (file: File): Promise<ImageData> =>
  new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Canvas 2D context unavailable"));
        return;
      }
      ctx.drawImage(img, 0, 0);
      resolve(ctx.getImageData(0, 0, canvas.width, canvas.height));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(i18n.t("signatureStamper:errors.imageReadFailed")));
    };
    img.src = url;
  });

/**
 * Otsu's method: pick the luminance threshold that best separates the two
 * histogram peaks (ink vs paper). Gives a sensible auto-default the user can
 * then fine-tune with the slider.
 */
export const otsuThreshold = (data: ImageData): number => {
  const hist = new Array<number>(256).fill(0);
  const px = data.data;
  let total = 0;
  for (let i = 0; i < px.length; i += 4) {
    // Ignore already-transparent pixels — they shouldn't bias the histogram.
    if ((px[i + 3] ?? 0) < 8) continue;
    const l = Math.round(luminance(px[i] ?? 0, px[i + 1] ?? 0, px[i + 2] ?? 0));
    hist[l] = (hist[l] ?? 0) + 1;
    total += 1;
  }
  if (total === 0) return 200;

  let sum = 0;
  for (let t = 0; t < 256; t += 1) sum += t * (hist[t] ?? 0);

  let sumB = 0;
  let wB = 0;
  let maxVar = -1;
  let threshold = 200;
  for (let t = 0; t < 256; t += 1) {
    wB += hist[t] ?? 0;
    if (wB === 0) continue;
    const wF = total - wB;
    if (wF === 0) break;
    sumB += t * (hist[t] ?? 0);
    const mB = sumB / wB;
    const mF = (sum - sumB) / wF;
    const between = wB * wF * (mB - mF) * (mB - mF);
    if (between > maxVar) {
      maxVar = between;
      threshold = t;
    }
  }
  return threshold;
};

const hexToRgb = (hex: string): [number, number, number] => {
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((c) => c + c)
          .join("")
      : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

/**
 * Produce a new ImageData with the paper turned transparent. The original is
 * never mutated. Existing alpha is respected (multiplied), so re-running on an
 * already-cleaned image is safe.
 */
export const removeBackground = (
  src: ImageData,
  opts: BgRemovalOptions,
): ImageData => {
  const { threshold, softness, recolor } = opts;
  const out = new ImageData(
    new Uint8ClampedArray(src.data),
    src.width,
    src.height,
  );
  const px = out.data;
  const ink = recolor ? hexToRgb(recolor) : null;
  const span = softness * 2;

  for (let i = 0; i < px.length; i += 4) {
    const a0 = px[i + 3] ?? 0;
    const lum = luminance(px[i] ?? 0, px[i + 1] ?? 0, px[i + 2] ?? 0);
    // factor: 1 = keep (ink), 0 = drop (paper), linear ramp between.
    let factor: number;
    if (span <= 0) {
      factor = lum <= threshold ? 1 : 0;
    } else {
      factor = (threshold + softness - lum) / span;
      factor = factor < 0 ? 0 : factor > 1 ? 1 : factor;
    }
    px[i + 3] = Math.round(a0 * factor);
    if (ink && factor > 0) {
      px[i] = ink[0];
      px[i + 1] = ink[1];
      px[i + 2] = ink[2];
    }
  }
  return out;
};

/** Render ImageData back to a PNG File (ready for the existing upload flow). */
export const imageDataToPngFile = (
  data: ImageData,
  filename: string,
): Promise<File> =>
  new Promise((resolve, reject) => {
    const canvas = document.createElement("canvas");
    canvas.width = data.width;
    canvas.height = data.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      reject(new Error("Canvas 2D context unavailable"));
      return;
    }
    ctx.putImageData(data, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error(i18n.t("signatureStamper:errors.pngEncodeFailed")));
        return;
      }
      const name = filename.replace(/\.[^.]+$/, "") + ".png";
      resolve(new File([blob], name, { type: "image/png" }));
    }, "image/png");
  });
