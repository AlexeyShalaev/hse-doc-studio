import type { Anchor, ThreadAnchor } from "../model/review.schema";

// Привязка комментария к фрагменту по цитате с контекстом (как TextQuoteSelector
// из W3C Web Annotation). Смещения в Anchor только подсказка: правки, в том числе
// пришедшие из git или от других участников, сдвигают текст, а цитата с
// контекстом остаётся. Сервер привязку не трактует, разрешает её клиент.

/** Сколько знаков до и после фрагмента сохраняется как контекст. */
export const CONTEXT_CHARS = 40;
/** Предел цитаты; совпадает с бэкендом (core.review.entities.QUOTE_MAX). */
export const QUOTE_MAX = 2000;
const MAX_CANDIDATES = 200;
const EDITED_WINDOW_FACTOR = 3;
const EDITED_WINDOW_SLACK = 60;
const PROBE = 16;

export type AnchorState = "ok" | "moved" | "edited" | "lost";

export type ResolvedAnchor =
  | { state: "lost"; from: null; to: null }
  | { state: Exclude<AnchorState, "lost">; from: number; to: number };

const LOST: ResolvedAnchor = { state: "lost", from: null, to: null };

export const makeAnchor = (text: string, from: number, to: number): Anchor => ({
  kind: "text",
  quote: text.slice(from, to),
  prefix: text.slice(Math.max(0, from - CONTEXT_CHARS), from),
  suffix: text.slice(to, to + CONTEXT_CHARS),
  start: from,
  end: to,
});

const commonSuffix = (a: string, b: string): number => {
  let n = 0;
  while (
    n < a.length &&
    n < b.length &&
    a[a.length - 1 - n] === b[b.length - 1 - n]
  )
    n++;
  return n;
};

const commonPrefix = (a: string, b: string): number => {
  let n = 0;
  while (n < a.length && n < b.length && a[n] === b[n]) n++;
  return n;
};

const occurrences = (text: string, quote: string): number[] => {
  const found: number[] = [];
  let at = text.indexOf(quote);
  while (at !== -1 && found.length < MAX_CANDIDATES) {
    found.push(at);
    at = text.indexOf(quote, at + 1);
  }
  return found;
};

const contextScore = (text: string, at: number, anchor: Anchor): number =>
  commonSuffix(
    text.slice(Math.max(0, at - CONTEXT_CHARS * 2), at),
    anchor.prefix,
  ) +
  commonPrefix(
    text.slice(
      at + anchor.quote.length,
      at + anchor.quote.length + CONTEXT_CHARS * 2,
    ),
    anchor.suffix,
  );

const byQuote = (text: string, anchor: Anchor): ResolvedAnchor | null => {
  const candidates = occurrences(text, anchor.quote);
  if (candidates.length === 0) return null;
  let best = candidates[0] ?? 0;
  let bestScore = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const at of candidates) {
    const score = contextScore(text, at, anchor);
    const distance = Math.abs(at - anchor.start);
    if (score > bestScore || (score === bestScore && distance < bestDistance)) {
      best = at;
      bestScore = score;
      bestDistance = distance;
    }
  }
  const to = best + anchor.quote.length;
  return { state: best === anchor.start ? "ok" : "moved", from: best, to };
};

/** Фрагмент внутри цитаты поправили: ищем то, что осталось между контекстом до и после. */
const byContext = (text: string, anchor: Anchor): ResolvedAnchor | null => {
  const before = anchor.prefix.slice(-PROBE);
  const after = anchor.suffix.slice(0, PROBE);
  if (before.length === 0 && after.length === 0) return null;
  const from = (() => {
    if (before.length === 0) return 0;
    const near = text.lastIndexOf(before, Math.max(0, anchor.start));
    const at = near !== -1 ? near : text.indexOf(before);
    return at === -1 ? null : at + before.length;
  })();
  if (from === null) return null;
  const window =
    anchor.quote.length * EDITED_WINDOW_FACTOR + EDITED_WINDOW_SLACK;
  const to = (() => {
    if (after.length === 0) return text.length;
    const at = text.indexOf(after, from);
    return at === -1 || at - from > window ? null : at;
  })();
  if (to === null || to <= from) return null;
  return { state: "edited", from, to };
};

export const resolveAnchor = (text: string, anchor: Anchor): ResolvedAnchor => {
  if (anchor.quote.length === 0) return LOST;
  const direct = text.slice(anchor.start, anchor.end) === anchor.quote;
  if (
    direct &&
    contextScore(text, anchor.start, anchor) ===
      anchor.prefix.length + anchor.suffix.length
  ) {
    return { state: "ok", from: anchor.start, to: anchor.end };
  }
  return byQuote(text, anchor) ?? byContext(text, anchor) ?? LOST;
};

/** Цитата треда для списка: у PDF-якоря это выделенный в PDF текст. */
export const quoteOf = (anchor: ThreadAnchor): string =>
  anchor.kind === "pdf" ? anchor.text : anchor.quote;
