import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// jsdom не считает стили по ширине окна, поэтому сворачивание кнопки в значок
// на узком экране проверяем по самой таблице стилей.
const css = readFileSync(
  join(import.meta.dirname, "../../../index.css"),
  "utf8",
);

describe("sync control narrow layout", () => {
  it("hides the words and keeps the icon and counts at 820px and below", () => {
    const block =
      /@media \(max-width: 820px\) \{\s*\/\*[^]*?\*\/\s*\.sync-label,\s*\.sync-when \{\s*display: none;/.exec(
        css,
      );
    expect(block).not.toBeNull();
  });

  it("never hides the counts or the icon", () => {
    expect(css).not.toMatch(/\.sync-count\s*\{[^}]*display:\s*none/);
    expect(css).not.toMatch(/\.sync-icon\s*\{[^}]*display:\s*none/);
  });

  it("respects reduced motion for the loading placeholder", () => {
    expect(css).toMatch(
      /prefers-reduced-motion: reduce\) \{\s*\.sync-control-skeleton \{\s*animation: none/,
    );
  });
});
