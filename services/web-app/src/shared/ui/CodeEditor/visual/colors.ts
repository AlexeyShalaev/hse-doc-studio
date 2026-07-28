/**
 * Resolve a LaTeX/xcolor color name to a CSS color for the visual editor.
 * A small curated palette (standard xcolor names + the HSE brand blue); an
 * unknown name or an xcolor mix (`blue!15`, `HTML{…}`) returns null so the
 * caller falls back to plain (un-colored) text rather than guessing.
 */

const NAMED: Record<string, string> = {
  red: "#e11",
  green: "#0a7d00",
  blue: "#1a1ae0",
  cyan: "#00b3b3",
  magenta: "#c000c0",
  yellow: "#d9a600",
  orange: "#e07800",
  brown: "#8b5a2b",
  pink: "#e56ba6",
  purple: "#8b1fbf",
  violet: "#6a1fe0",
  teal: "#008080",
  olive: "#7d7d00",
  lime: "#5aab00",
  black: "#111111",
  white: "#ffffff",
  gray: "#808080",
  grey: "#808080",
  darkgray: "#555555",
  darkgrey: "#555555",
  lightgray: "#b8b8b8",
  lightgrey: "#b8b8b8",
  // HSE brand palette (see reference_vkr_pres_sample).
  hseblue: "#102D69",
  hsedarkblue: "#0a1f4d",
};

export const colorToCss = (name: string): string | null => {
  const key = name.trim();
  const direct = NAMED[key] ?? NAMED[key.toLowerCase()];
  if (direct) return direct;
  if (/^#?[0-9a-fA-F]{6}$/.test(key))
    return key.startsWith("#") ? key : `#${key}`;
  if (/^#?[0-9a-fA-F]{3}$/.test(key))
    return key.startsWith("#") ? key : `#${key}`;
  return null; // xcolor mixes / unknown → caller shows plain text
};
