import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Контраст текста на цветных метках (WCAG AA, 4.5:1) считаем прямо по токенам
 * из index.css: jsdom не вычисляет цвета. Метка «черновик», «Замечание»,
 * «новое» и подобные рисуются цветом тона по его мягкой подложке (-soft),
 * а подложка лежит на одной из поверхностей bg-0..bg-3 (и bg-hover под строкой). Проверяем каждую
 * такую тройку и сплошную метку (accent-ink на accent).
 */

const css = readFileSync(join(import.meta.dirname, "index.css"), "utf8");

type Rgba = { r: number; g: number; b: number; a: number };

const themeBlock = (selector: string): string => {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no block for ${selector}`);
  const end = css.indexOf("\n  }", start);
  return css.slice(start, end);
};

const readVars = (block: string): Record<string, string> => {
  const vars: Record<string, string> = {};
  for (const m of block.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    vars[m[1]] = m[2].trim();
  }
  return vars;
};

const rootVars = readVars(themeBlock(":root"));

const THEMES: Record<string, Record<string, string>> = {
  dark: { ...rootVars, ...readVars(themeBlock('[data-theme="dark"]')) },
  light: { ...rootVars, ...readVars(themeBlock('[data-theme="light"]')) },
  blueprint: {
    ...rootVars,
    ...readVars(themeBlock('[data-theme="blueprint"]')),
  },
};

const resolve = (value: string, vars: Record<string, string>): string =>
  value.replace(/var\(--([\w-]+)\)/g, (_, name: string) => {
    const v = vars[name];
    if (v === undefined) throw new Error(`unknown token --${name}`);
    return resolve(v, vars);
  });

const toGamma = (c: number): number => {
  const x = Math.min(1, Math.max(0, c));
  return x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055;
};

// OKLCH → sRGB (0..1). Вне охвата sRGB каналы обрезаются.
const oklch = (l: number, c: number, hDeg: number) => {
  const h = (hDeg * Math.PI) / 180;
  const a = c * Math.cos(h);
  const b = c * Math.sin(h);
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return {
    r: toGamma(4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_),
    g: toGamma(-1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_),
    b: toGamma(-0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_),
  };
};

const parseColor = (raw: string): Rgba => {
  const v = raw.trim();
  let m = /^#([0-9a-f]{6})$/i.exec(v);
  if (m) {
    const n = parseInt(m[1], 16);
    return {
      r: ((n >> 16) & 255) / 255,
      g: ((n >> 8) & 255) / 255,
      b: (n & 255) / 255,
      a: 1,
    };
  }
  m = /^rgba?\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\s*\)$/.exec(
    v,
  );
  if (m) {
    return {
      r: Number(m[1]) / 255,
      g: Number(m[2]) / 255,
      b: Number(m[3]) / 255,
      a: m[4] === undefined ? 1 : Number(m[4]),
    };
  }
  m =
    /^oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\s*\)$/.exec(
      v,
    );
  if (m) {
    return {
      ...oklch(Number(m[1]) / 100, Number(m[2]), Number(m[3])),
      a: m[4] === undefined ? 1 : Number(m[4]),
    };
  }
  throw new Error(`unsupported color: ${v}`);
};

const over = (top: Rgba, bottom: Rgba): Rgba => ({
  r: top.r * top.a + bottom.r * (1 - top.a),
  g: top.g * top.a + bottom.g * (1 - top.a),
  b: top.b * top.a + bottom.b * (1 - top.a),
  a: 1,
});

const luminance = ({ r, g, b }: Rgba): number => {
  const lin = (c: number) =>
    c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
};

const contrast = (fg: Rgba, bg: Rgba): number => {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
};

const color = (vars: Record<string, string>, name: string): Rgba =>
  parseColor(resolve(`var(--${name})`, vars));

const TONES = ["accent", "c-ok", "c-warn", "c-err", "c-info"] as const;
const SURFACES = ["bg-0", "bg-1", "bg-2", "bg-3", "bg-hover"] as const;
const AA = 4.5;

const chipContrast = (
  vars: Record<string, string>,
  tone: string,
  surface: string,
): number => {
  const ground = over(color(vars, `${tone}-soft`), color(vars, surface));
  return contrast(color(vars, tone), ground);
};

describe("design tokens reach WCAG AA for text", () => {
  for (const [theme, vars] of Object.entries(THEMES)) {
    describe(theme, () => {
      for (const tone of TONES) {
        it(`${tone} text on its soft chip over ${SURFACES.join("/")}`, () => {
          for (const surface of SURFACES) {
            const ratio = chipContrast(vars, tone, surface);
            expect(
              ratio,
              `${theme}: ${tone} on ${tone}-soft over ${surface} = ${ratio.toFixed(2)}`,
            ).toBeGreaterThanOrEqual(AA);
          }
        });
      }

      it("accent-ink on a solid accent chip", () => {
        const ratio = contrast(
          color(vars, "accent-ink"),
          color(vars, "accent"),
        );
        expect(ratio).toBeGreaterThanOrEqual(AA);
      });

      it("body text levels fg-0..fg-1 on every surface", () => {
        for (const fg of ["fg-0", "fg-1"]) {
          for (const surface of SURFACES) {
            const ratio = contrast(color(vars, fg), color(vars, surface));
            expect(
              ratio,
              `${theme}: ${fg} on ${surface} = ${ratio.toFixed(2)}`,
            ).toBeGreaterThanOrEqual(AA);
          }
        }
      });
    });
  }
});
