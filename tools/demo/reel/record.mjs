// Записывает «киношный» тур по HSE Doc Studio через Playwright — 4 варианта:
// ru/en × light/dark. Хореография (титры, подписи, курсор) — page.evaluate +
// Web Animations API. Палитра директора — фирменные токены сайта.
//
// ЗАХВАТ: НЕ recordVideo (VP8-скринкаст Playwright «мылит» текст и пишет только
// в CSS-размере вьюпорта), а сырые PNG-кадры через CDP Page.startScreencast +
// свои таймстемпы → сборка ffmpeg concat в capture.mp4 без потерь качества.
//
// Требует запущенный демо-инстанс: `make demo-up`.
// Выход: .build/out/<lang>-<theme>/capture.mp4  (дальше — reel/compose.sh)
import { chromium } from "playwright";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE || "http://127.0.0.1:17777";
const OUTROOT = process.env.OUT || resolve(HERE, ".build/out");
const MANIFEST = JSON.parse(readFileSync(resolve(HERE, "../.build/demo/manifest.json"), "utf-8"));
const W = 1600, H = 1000;
const THESIS = "thesis";

const VARIANTS = (process.env.VARIANTS || "ru-light,ru-dark,en-light,en-dark").split(",");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── захват: PNG-кадры через CDP + ffconcat с реальными длительностями ──────
async function startCapture(page, framesDir) {
  mkdirSync(framesDir, { recursive: true });
  const cdp = await page.context().newCDPSession(page);
  const cap = { cdp, framesDir, i: 0, ts: [], stopped: false };
  cdp.on("Page.screencastFrame", (f) => {
    // запоздалые кадры после stopCapture молча пропускаем (папка уже удалена)
    if (!cap.stopped) {
      try {
        writeFileSync(
          `${framesDir}/f${String(cap.i).padStart(6, "0")}.png`,
          Buffer.from(f.data, "base64"),
        );
        cap.ts.push(f.metadata?.timestamp ?? 0);
        cap.i++;
      } catch {}
    }
    cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", {
    format: "png",
    everyNthFrame: 1,
    maxWidth: W * 2,
    maxHeight: H * 2,
  });
  return cap;
}

async function stopCapture(cap, outFile) {
  cap.stopped = true;
  await cap.cdp.send("Page.stopScreencast").catch(() => {});
  await cap.cdp.detach().catch(() => {});
  if (cap.i === 0) throw new Error("no frames captured");
  const lines = ["ffconcat version 1.0"];
  for (let i = 0; i < cap.i; i++) {
    // длительность кадра = до следующего таймстемпа; хвостовой держим 0.8 c
    const d = i + 1 < cap.ts.length ? Math.max(cap.ts[i + 1] - cap.ts[i], 1 / 60) : 0.8;
    lines.push(`file 'f${String(i).padStart(6, "0")}.png'`);
    lines.push(`duration ${d.toFixed(4)}`);
  }
  writeFileSync(`${cap.framesDir}/list.ffconcat`, lines.join("\n") + "\n");
  const res = spawnSync(
    "ffmpeg",
    ["-y", "-f", "concat", "-safe", "0", "-i", `${cap.framesDir}/list.ffconcat`,
      "-fps_mode", "vfr", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "12",
      "-preset", "fast", outFile, "-loglevel", "error"],
    { stdio: "inherit" },
  );
  if (res.status !== 0) throw new Error("ffmpeg assembly failed");
  rmSync(cap.framesDir, { recursive: true, force: true });
}

// ── тексты ──────────────────────────────────────────────────────────────────
const T = {
  ru: {
    tagline: "От пустой формы — до подписанного PDF.",
    outro: "Локально · Docker · Открытый код",
    caps: {
      welcome: "Все документы ВКР и курсовой — в одном проекте",
      side: "Слева исходник — справа то, что примут",
      side2: "Готовый PDF листается прямо в Студии",
      checks: "Нормоконтроль по ГОСТ: замечания приходят на поля",
      checks2: "Каждое правило можно отключить или сменить ему уровень",
      submit: "Пакет сдачи собирается сам — с подписями и анкетами",
      submit2: "Архив с каноническими именами — одной кнопкой",
      versions: "Каждая правка и сборка — в истории",
    },
    package_btn: "Упаковать",
    rules_btn: "Правила",
    nav_submit: "Сдача",
    nav_history: "История",
  },
  en: {
    tagline: "From a blank form — to a signed PDF.",
    outro: "Local · Docker · Open source",
    caps: {
      welcome: "Your whole thesis — documents, checks, builds — in one project",
      side: "Source on the left, the accepted PDF on the right",
      side2: "The built PDF scrolls right inside the Studio",
      checks: "GOST normcontrol: findings land in the margins",
      checks2: "Every rule can be disabled or re-levelled",
      submit: "The submission package assembles itself — signatures included",
      submit2: "A canonical-names archive — one click",
      versions: "Every edit and build — in the history",
    },
    package_btn: "Package",
    rules_btn: "Rules",
    nav_submit: "Submission",
    nav_history: "History",
  },
};

// ── палитра директора: токены 01-tokens.css ────────────────────────────────
const D = {
  light: {
    titleBg: "radial-gradient(1200px 700px at 50% 35%, #FFFDF8 0%, #F1EBDF 55%, #E3DACA 100%)",
    titleInk: "#17140F", titleSub: "#423C32", logoBg: "#17140F", logoInk: "#FAF7F0",
    capBg: "rgba(23,20,15,.85)", capInk: "#FAF7F0",
    cursor: "rgba(23,20,15,.85)", halo: "rgba(29,62,143,.20)", ring: "rgba(29,62,143,.9)", ringSoft: "rgba(29,62,143,.16)",
  },
  dark: {
    titleBg: "radial-gradient(1200px 700px at 50% 35%, #262119 0%, #1C1916 55%, #0E0C0A 100%)",
    titleInk: "#F2EDE2", titleSub: "#C8C0B1", logoBg: "#F2EDE2", logoInk: "#14120F",
    capBg: "rgba(14,12,10,.85)", capInk: "#F2EDE2",
    cursor: "rgba(242,237,226,.92)", halo: "rgba(157,184,255,.22)", ring: "rgba(157,184,255,.9)", ringSoft: "rgba(157,184,255,.16)",
  },
};

async function dirInit(page, th) {
  await page.addStyleTag({
    content: `
    #reel-cursor{position:fixed;z-index:2147483647;width:22px;height:22px;margin:-11px 0 0 -11px;
      border-radius:50%;background:${th.cursor};box-shadow:0 0 0 6px ${th.halo},0 4px 14px rgba(0,0,0,.3);
      pointer-events:none;left:50%;top:60%;transition:none}
    #reel-cap{position:fixed;z-index:2147483646;left:0;right:0;bottom:44px;display:flex;justify-content:center;pointer-events:none}
    #reel-cap .b{max-width:78%;padding:15px 30px;border-radius:14px;background:${th.capBg};
      color:${th.capInk};font:600 29px/1.25 'Golos Text',-apple-system,'Segoe UI',Roboto,sans-serif;
      letter-spacing:.2px;box-shadow:0 12px 40px rgba(0,0,0,.3);backdrop-filter:blur(8px);opacity:0;text-align:center}
    #reel-ring{position:fixed;z-index:2147483645;border:3px solid ${th.ring};border-radius:14px;
      box-shadow:0 0 0 4px ${th.ringSoft};pointer-events:none;opacity:0}
    #reel-title{position:fixed;inset:0;z-index:2147483647;display:flex;flex-direction:column;align-items:center;
      justify-content:center;gap:16px;background:${th.titleBg};color:${th.titleInk};text-align:center;opacity:0}
    #reel-title .logo{width:96px;height:96px;border-radius:24px;background:${th.logoBg};color:${th.logoInk};
      display:flex;align-items:center;justify-content:center;font:800 46px/1 'STIX Two Text',Georgia,serif;
      box-shadow:0 20px 60px rgba(0,0,0,.25)}
    #reel-title h1{font:600 64px/1.08 'STIX Two Text',Georgia,'Times New Roman',serif;letter-spacing:-.015em;margin:6px 0 0}
    #reel-title p{font:500 28px/1.3 'Golos Text',sans-serif;color:${th.titleSub};margin:0}
    #reel-title .url{font:600 21px/1 'JetBrains Mono',ui-monospace,monospace;opacity:.55;margin-top:8px}
    `,
  });
  await page.evaluate(() => {
    if (!document.getElementById("reel-cursor")) {
      const c = document.createElement("div"); c.id = "reel-cursor"; document.body.appendChild(c);
      const cap = document.createElement("div"); cap.id = "reel-cap";
      cap.innerHTML = '<div class="b"></div>'; document.body.appendChild(cap);
      const ring = document.createElement("div"); ring.id = "reel-ring"; document.body.appendChild(ring);
    }
  });
}

async function titleCard(page, title, sub, url, ms = 3000) {
  await page.evaluate(({ title, sub, url }) => {
    const el = document.createElement("div"); el.id = "reel-title";
    el.innerHTML = `<div class="logo">Д</div><h1>${title}</h1><p>${sub}</p>${url ? `<div class="url">${url}</div>` : ""}`;
    document.body.appendChild(el);
    el.animate([{ opacity: 0, transform: "scale(1.04)" }, { opacity: 1, transform: "scale(1)" }],
      { duration: 600, easing: "cubic-bezier(.2,.7,.2,1)", fill: "forwards" });
    el.querySelector("h1").animate([{ opacity: 0, transform: "translateY(14px)" }, { opacity: 1, transform: "none" }],
      { duration: 700, delay: 150, easing: "cubic-bezier(.2,.7,.2,1)", fill: "backwards" });
    el.querySelector("p").animate([{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }],
      { duration: 700, delay: 320, easing: "cubic-bezier(.2,.7,.2,1)", fill: "both" });
  }, { title, sub, url });
  await sleep(ms);
  await page.evaluate(() => {
    const el = document.getElementById("reel-title"); if (!el) return;
    const a = el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 520, easing: "ease", fill: "forwards" });
    a.onfinish = () => el.remove();
  });
  await sleep(560);
}

async function caption(page, text) {
  await page.evaluate((text) => {
    const b = document.querySelector("#reel-cap .b"); if (!b) return;
    b.getAnimations?.().forEach((a) => a.cancel());
    b.textContent = text;
    b.animate([{ opacity: 0, transform: "translateY(16px)" }, { opacity: 1, transform: "none" }],
      { duration: 520, easing: "cubic-bezier(.2,.7,.2,1)", fill: "forwards" });
  }, text);
}
async function captionOut(page) {
  await page.evaluate(() => {
    const b = document.querySelector("#reel-cap .b"); if (!b) return;
    b.animate([{ opacity: 1 }, { opacity: 0, transform: "translateY(10px)" }], { duration: 360, fill: "forwards" });
  });
  await sleep(380);
}

async function cursorTo(page, sel, dur = 900) {
  // ВАЖНО: без timeout boundingBox ждёт отсутствующий селектор 30 секунд —
  // ролик замирает на сцене (плавали, знаем). Нет элемента за 2 c — едем дальше.
  const box = await page.locator(sel).first().boundingBox({ timeout: 2000 }).catch(() => null);
  if (!box) return null;
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  await page.evaluate(({ x, y, dur }) => {
    const c = document.getElementById("reel-cursor"); if (!c) return;
    const cur = c.getBoundingClientRect();
    c.animate([{ left: cur.left + "px", top: cur.top + "px" }, { left: x + "px", top: y + "px" }],
      { duration: dur, easing: "cubic-bezier(.5,0,.15,1)", fill: "forwards" });
  }, { x, y, dur });
  await sleep(dur);
  return box;
}

async function ripple(page, halo) {
  await page.evaluate((halo) => {
    const c = document.getElementById("reel-cursor"); if (!c) return;
    c.animate([{ boxShadow: `0 0 0 6px ${halo},0 4px 14px rgba(0,0,0,.3)` },
      { boxShadow: `0 0 0 22px rgba(0,0,0,0),0 4px 14px rgba(0,0,0,.3)` }], { duration: 550, easing: "ease-out" });
  }, halo);
  await sleep(280);
}

// Плавный скролл контейнера: первый подходящий из sels, иначе — самый крупный
// скроллируемый элемент внутри main (селекторы панелей меняются, скролл — нет).
async function smoothScroll(page, sels, dy, ms = 1400) {
  await page
    .evaluate(
      ({ sels, dy, ms }) => {
        const pick = () => {
          for (const s of sels) {
            const el = document.querySelector(s);
            if (el && el.scrollHeight > el.clientHeight + 100) return el;
          }
          let best = null;
          for (const el of document.querySelectorAll("main, main *")) {
            const st = getComputedStyle(el);
            if (/(auto|scroll)/.test(st.overflowY) && el.scrollHeight > el.clientHeight + 150) {
              if (!best || el.clientHeight > best.clientHeight) best = el;
            }
          }
          return best;
        };
        const el = pick();
        if (!el) return;
        const start = el.scrollTop;
        const t0 = performance.now();
        return new Promise((res) => {
          const step = (t) => {
            const k = Math.min(1, (t - t0) / ms);
            const e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
            el.scrollTop = start + dy * e;
            if (k < 1) requestAnimationFrame(step);
            else res();
          };
          requestAnimationFrame(step);
        });
      },
      { sels, dy, ms },
    )
    .catch(() => {});
  await sleep(150);
}

async function waitPdf(page) {
  await page
    .waitForFunction(() => {
      const c = document.querySelector("canvas.pdf-page-canvas");
      return c && c.width > 0;
    }, { timeout: 20000 })
    .catch(() => {});
}

async function scene(page, th, url, settleMs = 900) {
  await page.goto(BASE + url, { waitUntil: "domcontentloaded" });
  await page.locator("nav.activity-bar").first().waitFor({ timeout: 8000 }).catch(() => {});
  await page.evaluate(() => window.scrollTo(0, 0));
  await sleep(settleMs);
  await dirInit(page, th);
  await sleep(200);
}

// ── прогон вариантов ────────────────────────────────────────────────────────
const browser = await chromium.launch();

for (const variant of VARIANTS) {
  const [lang, theme] = variant.split("-");
  const t = T[lang], th = D[theme];
  const projectId = MANIFEST[lang].id;
  const outDir = resolve(OUTROOT, variant);
  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });
  console.log("→ record", variant);

  const ctx = await browser.newContext({
    // CDP-скринкаст отдаёт кадры в CSS-размере вьюпорта (проверено): dsf выше 1
    // не даёт супсемплинга, только замедляет рендер (2× PDF тянет ожидания) —
    // поэтому dsf=1, а резкость обеспечивают lossless-PNG кадры вместо VP8.
    viewport: { width: W, height: H }, deviceScaleFactor: 1,
    colorScheme: theme === "dark" ? "dark" : "light",
    locale: lang === "ru" ? "ru-RU" : "en-US",
  });
  await ctx.addInitScript(
    ([theme, lang]) => {
      try {
        localStorage.setItem("hse-studio-theme",
          JSON.stringify({ state: { theme, density: "comfortable", lang }, version: 0 }));
        localStorage.setItem("hse-studio-workbench",
          JSON.stringify({ state: { activity: "documents", sidebarCollapsed: false, systemChatOpen: false }, version: 0 }));
      } catch {}
    },
    [theme, lang],
  );
  const page = await ctx.newPage();
  const cap = await startCapture(page, resolve(outDir, "frames"));

  // интро: титр поверх welcome, пока тот догружается
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  await dirInit(page, th);
  await titleCard(page, "HSE Doc Studio", t.tagline, "", 2600);
  await caption(page, t.caps.welcome);
  await cursorTo(page, ".card.hover", 750);
  await ripple(page, th.halo);
  await sleep(700);
  await cursorTo(page, ".card.hover >> nth=2", 800); // пробегаем по карточкам
  await sleep(1100);
  await captionOut(page);

  // «Рядом»: превью → side-by-side → листаем готовый PDF
  await scene(page, th, `/projects/${projectId}/documents/${THESIS}`, 500);
  await waitPdf(page);
  await sleep(500);
  await caption(page, t.caps.side);
  await cursorTo(page, "#document-tab-side", 750);
  await ripple(page, th.halo);
  await page.locator("#document-tab-side").click().catch(() => {});
  await waitPdf(page);
  await sleep(450);
  await page.keyboard.press("Escape"); // ящик «Навигация» поверх текста
  await sleep(1900);
  await caption(page, t.caps.side2);
  await smoothScroll(page, ['[role="document"]'], 900, 1600);
  await sleep(500);
  await smoothScroll(page, ['[role="document"]'], 900, 1600);
  await sleep(1100);
  await captionOut(page);

  // замечания: переходим ВКЛАДКОЙ (SPA, без белой вспышки перезагрузки)
  await cursorTo(page, "#document-tab-checks", 700);
  await ripple(page, th.halo);
  await page.locator("#document-tab-checks").click({ timeout: 2500 }).catch(() => {});
  await sleep(500);
  if (!page.url().includes("tab=checks")) {
    await scene(page, th, `/projects/${projectId}/documents/${THESIS}?tab=checks`, 800);
  }
  await page.locator("nav.activity-bar .activity-item").nth(1).click().catch(() => {});
  await sleep(600);
  await caption(page, t.caps.checks);
  await sleep(2300);
  await smoothScroll(page, [], 700, 1500);
  await sleep(900);
  const rulesBtn = page.locator("main button", { hasText: t.rules_btn }).first();
  await cursorTo(page, `main button:has-text("${t.rules_btn}")`, 750);
  await ripple(page, th.halo);
  await rulesBtn.click({ timeout: 2500 }).catch(() => {});
  await sleep(500);
  await caption(page, t.caps.checks2);
  await sleep(2400);
  await captionOut(page);

  // сдача: кнопкой Activity Bar (SPA), состав пакета → кнопка «Упаковать»
  await cursorTo(page, `nav.activity-bar button:has-text("${t.nav_submit}")`, 700);
  await ripple(page, th.halo);
  await page
    .locator("nav.activity-bar button", { hasText: t.nav_submit })
    .first()
    .click({ timeout: 2500 })
    .catch(() => {});
  await sleep(700);
  if (!page.url().includes("/submit")) {
    await scene(page, th, `/projects/${projectId}/submit`, 1100);
  } else {
    await sleep(700);
  }
  await caption(page, t.caps.submit);
  await sleep(2300);
  await smoothScroll(page, [], 700, 1600);
  await sleep(700);
  await caption(page, t.caps.submit2);
  await cursorTo(page, `main button:has-text("${t.package_btn}")`, 850);
  await ripple(page, th.halo);
  await sleep(2100);
  await captionOut(page);

  // история: кнопкой Activity Bar (SPA), лента версий
  await cursorTo(page, `nav.activity-bar button:has-text("${t.nav_history}")`, 700);
  await ripple(page, th.halo);
  await page
    .locator("nav.activity-bar button", { hasText: t.nav_history })
    .first()
    .click({ timeout: 2500 })
    .catch(() => {});
  await sleep(700);
  if (!page.url().includes("/versions")) {
    await scene(page, th, `/projects/${projectId}/versions`, 1100);
  } else {
    await sleep(800);
  }
  await caption(page, t.caps.versions);
  await sleep(2200);
  await smoothScroll(page, [], 600, 1500);
  await sleep(1700);
  await captionOut(page);

  // аутро
  await titleCard(page, "HSE Doc Studio", t.outro, "github.com/AlexeyShalaev/hse-doc-studio", 3000);

  await sleep(400);
  await stopCapture(cap, resolve(outDir, "capture.mp4"));
  await page.close();
  await ctx.close();
  console.log("  done", variant, `(${cap.i} frames)`);
}

await browser.close();
console.log("RECORD_DONE →", OUTROOT);
