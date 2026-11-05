import { expect, type Page } from "@playwright/test";
import { seedPassword } from "./helpers";

/** Общее для телефонных сценариев (mobile.spec.ts, mobile-admin.spec.ts). */
export const SIZES = [
  { width: 360, height: 740 },
  { width: 390, height: 844 },
] as const;

export const MIN_TOUCH = 40;

/** Вход на экране /login: на телефоне лендинг прячет форму в окно, а прямой адрес даёт её сразу. */
export const loginOnPhone = async (
  page: Page,
  email: string,
  password: string = seedPassword(),
): Promise<void> => {
  await page.goto("/login");
  await page.locator("input[type=email]").fill(email);
  await page.locator("input[type=password]").fill(password);
  await page.locator("form button[type=submit]").first().click();
  await expect(page.getByTestId("account-menu-trigger")).toBeVisible();
};

/**
 * Элементы, торчащие за правый край окна. Страница приложения не прокручивается (body: overflow hidden),
 * поэтому scrollWidth ничего не скажет: ищем сами элементы, не спрятанные внутри блока со своей прокруткой.
 */
export const overflowing = (page: Page): Promise<string[]> =>
  page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const clipped = (el: Element): boolean => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        if (getComputedStyle(p).overflowX === "visible") continue;
        if (p.getBoundingClientRect().right <= viewport + 1) return true;
      }
      return false;
    };
    const found: string[] = [];
    for (const el of document.querySelectorAll("body *")) {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      if (getComputedStyle(el).position === "fixed") continue;
      if (rect.right > viewport + 1 && !clipped(el)) {
        found.push(
          `${el.tagName.toLowerCase()}.${String(el.className)} right=${String(Math.round(rect.right))}`,
        );
      }
    }
    return found.slice(0, 8);
  });

export const expectNoHorizontalScroll = async (page: Page): Promise<void> => {
  const dims = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(dims.scroll).toBeLessThanOrEqual(dims.client);
  expect(await overflowing(page)).toEqual([]);
};

export const expectTouchTarget = async (
  page: Page,
  locator: ReturnType<Page["locator"]>,
  what: string,
): Promise<void> => {
  const box = await locator.boundingBox();
  expect(box, what).not.toBeNull();
  expect(box?.width ?? 0, `${what}: ширина`).toBeGreaterThanOrEqual(MIN_TOUCH);
  expect(box?.height ?? 0, `${what}: высота`).toBeGreaterThanOrEqual(MIN_TOUCH);
};


/**
 * Содержимое, обрезанное справа блоком с overflow (hidden, auto, scroll): кнопка, у которой видна половина, или
 * строка, ушедшая за край. Намеренные полосы прокрутки (вкладки, панели инструментов) и обрезка с многоточием не в счёт.
 */
export const clippedContent = (page: Page): Promise<string[]> =>
  page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const ignore =
      ".tabs, .pdf-toolbar, .visual-format-toolbar, .source-editor-toolbar, .cm-scroller, .pdf-scroll, .tbl-cards thead, [data-hscroll]";
    const name = (el: Element): string =>
      `${el.tagName.toLowerCase()}.${String(el.className).split(" ").filter(Boolean).slice(0, 2).join(".")}`;
    const found = new Set<string>();
    for (const el of document.querySelectorAll("body *")) {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      if (getComputedStyle(el).position === "fixed") continue;
      if (el.closest("[aria-hidden=true], .sr-only") || el.closest(ignore)) continue;
      for (let parent = el.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        if (style.overflowX === "visible") continue;
        if (style.textOverflow === "ellipsis") break;
        const box = parent.getBoundingClientRect();
        if (rect.right > box.right + 1.5 && rect.left < box.right) {
          found.add(`${name(parent)} режет ${name(el)} (${String(Math.round(rect.right))} > ${String(Math.round(box.right))})`);
        }
        break;
      }
      if (rect.right > viewport + 1) {
        let inside = false;
        for (let parent = el.parentElement; parent; parent = parent.parentElement) {
          if (getComputedStyle(parent).overflowX !== "visible" && parent.getBoundingClientRect().right <= viewport + 1) {
            inside = true;
            break;
          }
        }
        if (!inside) found.add(`за окном: ${name(el)} (${String(Math.round(rect.right))})`);
      }
    }
    return [...found].slice(0, 8);
  });

export const expectNothingClipped = async (page: Page, where?: string): Promise<void> => {
  expect(await clippedContent(page), where ?? page.url()).toEqual([]);
};

/** Интерактивные элементы первого экрана меньше минимума: пустой список значит, что цели достаточны. */
export const smallTargets = (page: Page): Promise<string[]> =>
  page.evaluate((min) => {
    const out: string[] = [];
    const nodes = document.querySelectorAll(
      "button, a[href], input, select, textarea, [role=button], [role=tab]",
    );
    for (const el of nodes) {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0 || el.closest("[aria-hidden=true], .sr-only")) continue;
      if (rect.top >= innerHeight || rect.bottom <= 0) continue;
      if (el instanceof HTMLInputElement && ["checkbox", "radio"].includes(el.type)) continue;
      if (el instanceof HTMLAnchorElement && getComputedStyle(el).display === "inline") continue;
      if (Math.min(rect.width, rect.height) < min - 0.5) {
        out.push(
          `${el.tagName.toLowerCase()} ${String(Math.round(rect.width))}x${String(Math.round(rect.height))} ${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 30)}`,
        );
      }
    }
    return out;
  }, MIN_TOUCH);

/** Размер текста до загрузки приложения: тот же ключ localStorage, что читает загрузочный скрипт. */
export const presetTextScale = async (page: Page, scale: number): Promise<void> => {
  await page.addInitScript((value) => {
    const raw = localStorage.getItem("hse-studio-theme");
    const stored = raw ? (JSON.parse(raw) as { state?: object; version?: number }) : {};
    localStorage.setItem(
      "hse-studio-theme",
      JSON.stringify({
        ...stored,
        version: stored.version ?? 0,
        state: { ...stored.state, textScale: value, textScaleChosen: value !== 100 },
      }),
    );
  }, scale);
};

/**
 * Содержимое панели, вылезающее за её рамку: элемент правее или левее границ панели, а также обрезанный текст без
 * многоточия (элемент с overflow hidden, у которого scrollWidth больше видимой ширины). Скрытые кнопки-меню строк
 * (нулевая ширина до наведения) и всплывающие слои не в счёт.
 */
export const escapesPanel = (page: Page, rootSelector: string): Promise<string[]> =>
  page.evaluate((selector) => {
    const root = document.querySelector(selector);
    if (!root) return [`нет элемента ${selector}`];
    const box = root.getBoundingClientRect();
    const name = (el: Element): string =>
      `${el.tagName.toLowerCase()}.${String(el.className).split(" ").filter(Boolean).slice(0, 2).join(".")} «${(el.textContent ?? "").trim().slice(0, 24)}»`;
    const found = new Set<string>();
    if (root.scrollWidth > root.clientWidth + 1) {
      found.add(`панель прокручивается вбок: ${String(root.scrollWidth)} > ${String(root.clientWidth)}`);
    }
    for (const el of root.querySelectorAll("*")) {
      if (el.closest("[aria-hidden=true], .sr-only, [aria-haspopup=menu]")) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      const style = getComputedStyle(el);
      if (style.position === "fixed" || style.visibility === "hidden") continue;
      if (rect.right > box.right + 0.5 || rect.left < box.left - 0.5) {
        found.add(`за рамкой: ${name(el)} (${String(Math.round(rect.left))}..${String(Math.round(rect.right))} при ${String(Math.round(box.left))}..${String(Math.round(box.right))})`);
      }
      const clips = style.overflowX === "hidden" || style.overflowX === "clip";
      if (clips && style.textOverflow !== "ellipsis" && el.clientWidth > 4 && el.scrollWidth > el.clientWidth + 1) {
        found.add(`обрезан без многоточия: ${name(el)} (${String(el.scrollWidth)} > ${String(el.clientWidth)})`);
      }
    }
    return [...found].slice(0, 10);
  }, rootSelector);

/** Пары элементов внутри блока, которые накладываются друг на друга больше чем на 1 px. */
export const overlapping = (page: Page, rootSelector: string, itemSelector: string): Promise<string[]> =>
  page.evaluate(
    ({ root, item }) => {
      const items = [...document.querySelectorAll(root)].flatMap((r) => [...r.querySelectorAll(item)]).filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });
      const label = (el: Element): string => `${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0] ?? ""} «${(el.textContent ?? "").trim().slice(0, 16)}»`;
      const out: string[] = [];
      for (let i = 0; i < items.length; i += 1) {
        for (let j = i + 1; j < items.length; j += 1) {
          const a = items[i]!.getBoundingClientRect();
          const b = items[j]!.getBoundingClientRect();
          if (items[i]!.contains(items[j]!) || items[j]!.contains(items[i]!)) continue;
          const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
          const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
          if (w > 1 && h > 1) out.push(`${label(items[i]!)} налезает на ${label(items[j]!)}`);
        }
      }
      return out.slice(0, 10);
    },
    { root: rootSelector, item: itemSelector },
  );
