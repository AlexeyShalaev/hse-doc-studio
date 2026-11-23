import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// jsdom не применяет медиазапросы, поэтому зоны касания проверяем по таблице стилей:
// при касании (pointer: coarse) кнопки и значки шапки не меньше 44px при любой ширине.
const css = readFileSync(join(import.meta.dirname, "index.css"), "utf8");

/** Тело блока `@media (pointer: coarse) {` с этим селектором первым (без вложенных скобок внутри правил). */
const coarseBlock = (firstSelector: string): string => {
  const head = `@media (pointer: coarse) {\n  ${firstSelector}`;
  const start = css.indexOf(head);
  if (start < 0) return "";
  const end = css.indexOf("\n}\n", start);
  return css.slice(start, end);
};

describe("зоны касания при pointer: coarse", () => {
  it("--touch-min 44px при касании, а не 36px десктопа", () => {
    expect(css).toMatch(
      /@media \(pointer: coarse\) \{\s*:root \{\s*--touch-min: max\(2\.75rem, 44px\);/,
    );
    // Переопределение стоит после телефонного (40px), иначе телефон с касанием остался бы при 40px.
    expect(css.indexOf("--touch-min: max(2.75rem, 44px)")).toBeGreaterThan(
      css.indexOf("--touch-min: max(2.5rem, 40px)"),
    );
  });

  it("кнопки, значки шапки, переключатели, вкладки и меню держат --touch-min при любой ширине", () => {
    const block = coarseBlock(".btn,");
    expect(block).not.toBe("");
    for (const selector of [
      ".icon-btn",
      ".seg button",
      ".tabs .tab",
      ".row-btn",
      ".adm-menu-item",
      ".titlebar",
      ".statusbar .seg-clickable",
    ]) {
      expect(block, selector).toContain(selector);
    }
    expect(block).toMatch(
      /\.icon-btn,\s*\.icon-btn\.sm \{\s*min-width: var\(--touch-min\);\s*min-height: var\(--touch-min\);\s*width: var\(--touch-min\);\s*height: var\(--touch-min\);/,
    );
    // Нет прежнего ограничения «только планшет» и мелких высот вроде 2rem или 1.75rem.
    expect(css).not.toContain(
      "@media (pointer: coarse) and (min-width: 768px) and (max-width: 1023.98px)",
    );
    expect(block).not.toMatch(/min-height: (2rem|1\.75rem)/);
  });
});
