// Playwright-скрипт скриншотов документации HSE Doc Studio.
// Снимает МАТРИЦУ: 2 языка интерфейса (ru/en) × 2 темы (light/dark) —
// сайт показывает кадр, совпадающий с темой и языком читателя.
//
// Требует запущенный демо-инстанс: `make demo-up` (tools/demo/run-demo.sh).
// Выход: docs/ru/assets/shots/<screen>.<lang>.<theme>.png
// (ассеты сайта общие: docs/ru — единственный источник, sync копирует в docs/en).
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE || "http://127.0.0.1:17777";
const OUT = process.env.OUT || resolve(HERE, "../../../docs/ru/assets/shots");
const MANIFEST = JSON.parse(readFileSync(resolve(HERE, "../.build/demo/manifest.json"), "utf-8"));

// Проект под язык интерфейса: RU-скрины — русская ВКР, EN-скрины — английская.
const PROJECT = { ru: MANIFEST.ru, en: MANIFEST.en };
const THESIS = "thesis";

const LANGS = (process.env.LANGS || "ru,en").split(",");
const THEMES = (process.env.THEMES || "light,dark").split(",");
const ONLY = process.env.ONLY ? new Set(process.env.ONLY.split(",")) : null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── экраны ──────────────────────────────────────────────────────────────────
// [имя, url(projectId), подготовка(page, lang)]
const SCREENS = [
  ["welcome", () => "/", null],
  ["wizard", () => "/wizard", null],
  [
    // флагман: «Рядом» — PDF и редактор на одном экране
    "workspace",
    (p) => `/projects/${p}/documents/${THESIS}`,
    async (page) => {
      await waitPdf(page);
      await page.locator("#document-tab-side").click();
      await waitPdf(page);
      await sleep(900);
      // визуальный редактор открывает ящик «Навигация» поверх текста — закрываем
      await page.keyboard.press("Escape");
      await sleep(400);
    },
  ],
  ["documents", (p) => `/projects/${p}/documents/${THESIS}`, waitPdf],
  ["compile", (p) => `/projects/${p}/documents/${THESIS}?tab=compile`, null],
  [
    "checks",
    (p) => `/projects/${p}/documents/${THESIS}?tab=checks`,
    async (page) => {
      // левая панель — «Замечания» (второй пункт Activity Bar)
      await page.locator("nav.activity-bar .activity-item").nth(1).click();
      await sleep(700);
    },
  ],
  ["submit", (p) => `/projects/${p}/submit`, null],
  ["signatures", (p) => `/projects/${p}/submit/signatures`, null],
  [
    "editor",
    (p) => `/projects/${p}/documents/${THESIS}?tab=source`,
    async (page, lang) => {
      // включаем визуальный режим, если тумблер найдётся (иначе остаётся код)
      const label = lang === "ru" ? "Визуальный" : "Visual";
      await page
        .getByRole("button", { name: label })
        .first()
        .click({ timeout: 4000 })
        .catch(() => {});
      await sleep(1200);
      await page.keyboard.press("Escape"); // ящик «Навигация» поверх текста
      await sleep(400);
    },
  ],
  ["versions", (p) => `/projects/${p}/versions`, null],
  [
    "agent",
    (p) => `/projects/${p}/documents/${THESIS}`,
    async (page, lang) => {
      await waitPdf(page);
      // чат открывается кнопкой «Агент» в Activity Bar (localStorage-трюк
      // с systemChatOpen не переживает гидратацию стора)
      await page
        .locator("nav.activity-bar button", { hasText: lang === "ru" ? "Агент" : "Agent" })
        .first()
        .click({ timeout: 4000 })
        .catch(() => {});
      await page.locator(".chat-dock").waitFor({ timeout: 8000 }).catch(() => {});
      await sleep(400);
      // пустое состояние → «Новый чат» → композер с живым черновиком запроса
      await page
        .locator(".chat-dock button", { hasText: lang === "ru" ? "Новый чат" : "New chat" })
        .first()
        .click({ timeout: 4000 })
        .catch(() => {});
      await page.locator(".agent-composer-textarea").waitFor({ timeout: 6000 }).catch(() => {});
      const draft =
        lang === "ru"
          ? "Проверь введение: кавычки и тире по ГОСТ — и поправь прямо в thesis.tex"
          : "Check the introduction: fix quotes and dashes per GOST right in thesis.tex";
      await page.locator(".agent-composer-textarea").fill(draft, { timeout: 4000 }).catch(() => {});
      await sleep(500);
    },
  ],
  ["settings", () => "/settings/appearance", async (page) => {
    await page.locator(".settings-modal").waitFor({ timeout: 8000 });
    await sleep(400);
  }],
  [
    // мастер первого запуска: натив всегда is_ready — мокаем «контейнер без
    // папки данных», как его видит настоящая установка из GHCR-образа
    "setup",
    () => "/",
    async (page) => {
      await page.route("**/api/v1/setup/status", (route) =>
        route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            is_ready: false,
            deployment_mode: "all-in-one",
            checks: [
              { id: "docker", severity: "ok", code: "ok", context: {} },
              { id: "project_storage", severity: "blocker", code: "no_host_path", context: {} },
            ],
            compose_project: null,
            can_self_apply: true,
            app_version: "0.1.0",
          }),
        }),
      );
      await page.route("**/api/v1/setup/environment", (route) =>
        route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            engine: {
              server_version: "28.4.0", os_type: "linux",
              operating_system: "Docker Desktop", architecture: "x86_64",
              cpus: 24, memory_bytes: 16718663680,
            },
            container: {
              image: "ghcr.io/alexeyshalaev/hse-doc-studio:latest",
              published_ports: ["17240:8000"], mounts: [],
              socket_mounted: true, group_add: ["0"],
              restart_policy: "unless-stopped", network_mode: "bridge",
            },
            fonts: { directory: null, count: 0 },
            tex: { image: "texlive/texlive:latest", present: false },
          }),
        }),
      );
      await page.reload({ waitUntil: "domcontentloaded" });
      await sleep(2200);
      // идём браузером папок в домашнюю Documents — чистый список и живая
      // проба вместо сырого содержимого C:/Users с предупреждением о правах
      await page.getByText("Alex Shalaev", { exact: true }).first().click({ timeout: 4000 }).catch(() => {});
      await sleep(900);
      await page.getByText("Documents", { exact: true }).first().click({ timeout: 4000 }).catch(() => {});
      await sleep(1800); // проба папки
      await page.unroute("**/api/v1/setup/status").catch(() => {});
      await page.unroute("**/api/v1/setup/environment").catch(() => {});
    },
  ],
];

async function waitPdf(page) {
  // pdf.js рендерит асинхронно: ждём холст с ненулевой шириной
  await page
    .waitForFunction(
      () => {
        const c = document.querySelector("canvas.pdf-page-canvas");
        return c && c.width > 0;
      },
      { timeout: 20000 },
    )
    .catch(() => {});
  await sleep(800);
}

// ── прогон матрицы ──────────────────────────────────────────────────────────
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();

for (const lang of LANGS) {
  for (const theme of THEMES) {
    const ctx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
      colorScheme: theme === "dark" ? "dark" : "light",
      locale: lang === "ru" ? "ru-RU" : "en-US",
    });
    // тема и язык — ДО загрузки приложения (boot-скрипт index.html читает ключ синхронно)
    await ctx.addInitScript(
      ([theme, lang]) => {
        try {
          localStorage.setItem(
            "hse-studio-theme",
            JSON.stringify({ state: { theme, density: "comfortable", lang }, version: 0 }),
          );
          localStorage.setItem(
            "hse-studio-workbench",
            JSON.stringify({
              state: { activity: "documents", sidebarCollapsed: false, systemChatOpen: false },
              version: 0,
            }),
          );
        } catch {}
      },
      [theme, lang],
    );

    const page = await ctx.newPage();
    const projectId = PROJECT[lang].id;

    for (const [name, urlOf, prepare] of SCREENS) {
      if (ONLY && !ONLY.has(name)) continue;
      const file = `${OUT}/${name}.${lang}.${theme}.png`;
      try {
        await page.goto(BASE + urlOf(projectId), { waitUntil: "domcontentloaded" });
        await page.waitForLoadState("networkidle").catch(() => {});
        await page.evaluate(() => document.fonts?.ready);
        await sleep(900);
        if (prepare) await prepare(page, lang);
        await page.screenshot({ path: file });
        console.log("shot", `${name}.${lang}.${theme}`);
      } catch (e) {
        console.log("FAIL", `${name}.${lang}.${theme}`, String(e).slice(0, 140));
      }
    }
    await ctx.close();
  }
}

await browser.close();
console.log("SHOTS_DONE →", OUT);
