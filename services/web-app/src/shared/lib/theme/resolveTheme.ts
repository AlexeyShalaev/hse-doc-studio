import type { Theme } from "./themeStore";

// A concrete theme that maps 1:1 onto a `[data-theme="…"]` CSS block. "system"
// is a *preference*, not a paintable value — it must be resolved to one of these
// before it ever reaches the DOM.
export type ResolvedTheme = "dark" | "light" | "blueprint";

export const PREFERS_DARK_QUERY = "(prefers-color-scheme: dark)";

// "system" follows the OS colour scheme (dark ↔ light); every explicit theme
// maps to itself. Callers pass the current prefers-color-scheme match so this
// stays a pure function (easy to test, no matchMedia inside).
export const resolveTheme = (
  theme: Theme,
  prefersDark: boolean,
): ResolvedTheme =>
  theme === "system" ? (prefersDark ? "dark" : "light") : theme;
