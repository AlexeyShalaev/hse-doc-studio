// Генерирует ассеты «киношного» фрейма ролика через Playwright-скриншоты.
// Для КАЖДОЙ темы свой фон в фирменных токенах сайта («бумага» / «тёмная бумага»):
//   bg.<theme>.png     — фон 1920×1080 (радиальный градиент в тон титрам)
//   shadow.<theme>.png — мягкая тень окна на прозрачном фоне
//   mask.png           — белое скруглённое окно на чёрном (alphamerge по luma, темонезависимо)
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const OUT = process.env.ASSETS_DIR || resolve(dirname(fileURLToPath(import.meta.url)), ".build/assets");
mkdirSync(OUT, { recursive: true });

// Всё в 2× (супсемплинг): запись идёт в 3200×2000, композиция — на 4K-холсте,
// финал даунскейлится в 1920×1080 — картинка резкая, без «мыла» скринкаста.
const FRAME_W = 3840, FRAME_H = 2160, WIN_W = 3200, WIN_H = 2000, R = 44;

// Палитры = токены 01-tokens.css сайта (бумага/чернила обеих схем).
const BG = {
  light: `radial-gradient(1400px 850px at 50% 22%, #FFFDF8 0%, #F1EBDF 52%, #E3DACA 100%)`,
  dark: `radial-gradient(1400px 850px at 50% 22%, #262119 0%, #1C1916 52%, #0E0C0A 100%)`,
};
const SHADOW = { light: "rgba(23,20,15,.38)", dark: "rgba(0,0,0,.7)" };

const browser = await chromium.launch();

async function shot(html, w, h, file, omit = false) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  await p.setContent(
    `<!doctype html><html><head><style>*{margin:0;padding:0;box-sizing:border-box}</style></head><body>${html}</body></html>`,
  );
  await p.screenshot({ path: `${OUT}/${file}`, omitBackground: omit, clip: { x: 0, y: 0, width: w, height: h } });
  await ctx.close();
}

for (const theme of ["light", "dark"]) {
  await shot(
    `<div style="width:${FRAME_W}px;height:${FRAME_H}px;background:${BG[theme]}"></div>`,
    FRAME_W, FRAME_H, `bg.${theme}.png`,
  );
  await shot(
    `<div style="position:relative;width:${FRAME_W}px;height:${FRAME_H}px">
       <div style="position:absolute;left:${(FRAME_W - WIN_W) / 2}px;top:${(FRAME_H - WIN_H) / 2 + 44}px;
         width:${WIN_W}px;height:${WIN_H}px;border-radius:${R}px;background:${SHADOW[theme]};filter:blur(68px)"></div></div>`,
    FRAME_W, FRAME_H, `shadow.${theme}.png`, true,
  );
}

await shot(
  `<div style="width:${WIN_W}px;height:${WIN_H}px;background:#000">
     <div style="width:${WIN_W}px;height:${WIN_H}px;border-radius:${R}px;background:#fff"></div></div>`,
  WIN_W, WIN_H, "mask.png",
);

await browser.close();
console.log("ASSETS_DONE");
