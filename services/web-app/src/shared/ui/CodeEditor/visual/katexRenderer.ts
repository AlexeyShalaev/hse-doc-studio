/**
 * Lazy KaTeX loader + render cache. KaTeX (and its CSS/fonts) is split into an
 * async chunk so code-mode users never pay for it; everything is bundled and
 * served same-origin (local-first, no CDN).
 */

import type katexDefault from "katex";

type Katex = typeof katexDefault;

let katexPromise: Promise<Katex> | null = null;

const loadKatex = (): Promise<Katex> =>
  (katexPromise ??= Promise.all([
    import("katex"),
    // Side-effect import: Vite emits and injects the stylesheet on demand.
    import("katex/dist/katex.min.css"),
  ]).then(([mod]) => mod.default));

// tex+mode → rendered HTML. Bounded so a formula-heavy thesis can't grow it
// without limit; Map iteration order gives cheap oldest-first eviction.
const CACHE_CAP = 300;
const cache = new Map<string, string>();

const cachedRender = (katex: Katex, tex: string, display: boolean): string => {
  const key = `${display ? "D" : "I"}:${tex}`;
  const hit = cache.get(key);
  if (hit !== undefined) return hit;
  const html = katex.renderToString(tex, {
    displayMode: display,
    throwOnError: false,
    strict: "ignore",
    output: "htmlAndMathml",
  });
  if (cache.size >= CACHE_CAP) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  cache.set(key, html);
  return html;
};

/**
 * Render `tex` into `el` once KaTeX is loaded. Until then the caller's
 * placeholder content (the raw source) stays visible. On a hard failure the
 * raw source is shown in the error style instead.
 */
export const renderMathInto = (
  el: HTMLElement,
  tex: string,
  display: boolean,
): void => {
  void loadKatex()
    .then((katex) => {
      // Rendering into an already-detached element is harmless; skipping would
      // race with toDOM(), which runs before the widget is attached.
      el.innerHTML = cachedRender(katex, tex, display);
      el.classList.remove("cm-vis-math-pending");
    })
    .catch(() => {
      el.textContent = tex;
      el.classList.remove("cm-vis-math-pending");
      el.classList.add("cm-vis-math-error");
    });
};
