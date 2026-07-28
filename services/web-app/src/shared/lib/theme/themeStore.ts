import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Lang } from "@shared/api";

// "system" tracks the OS colour scheme; the other three are explicit themes.
// The stored value is a *preference* — `resolveTheme` turns "system" into a
// concrete theme before it is written to `data-theme`.
export type Theme = "system" | "dark" | "light" | "blueprint";
export type Density = "comfortable" | "compact";

type ThemeState = {
  theme: Theme;
  density: Density;
  lang: Lang;
};

type ThemeActions = {
  setTheme: (theme: Theme) => void;
  setDensity: (density: Density) => void;
  setLang: (lang: Lang) => void;
  cycleTheme: () => void;
  toggleDensity: () => void;
  toggleLang: () => void;
};

const THEME_ORDER: readonly Theme[] = ["system", "dark", "light", "blueprint"];

// First-run interface language: the index.html inline boot script resolves it
// (persisted value → navigator auto-detect → "ru") into `window.__INITIAL_LANG__`
// before any module loads. zustand-persist overrides this with the stored value
// for returning users, so this only seeds a brand-new visitor.
const initialLang = (): Lang => {
  const injected =
    typeof window !== "undefined" ? window.__INITIAL_LANG__ : undefined;
  return injected === "ru" || injected === "en" ? injected : "ru";
};

export const useThemeStore = create<ThemeState & ThemeActions>()(
  persist(
    (set, get) => ({
      theme: "system",
      density: "comfortable",
      lang: initialLang(),
      setTheme: (theme: Theme) => {
        set({ theme });
      },
      setDensity: (density: Density) => {
        set({ density });
      },
      setLang: (lang: Lang) => {
        set({ lang });
      },
      cycleTheme: () => {
        const current = get().theme;
        const idx = THEME_ORDER.indexOf(current);
        const next = THEME_ORDER[(idx + 1) % THEME_ORDER.length] ?? "system";
        set({ theme: next });
      },
      toggleDensity: () => {
        set({
          density: get().density === "comfortable" ? "compact" : "comfortable",
        });
      },
      toggleLang: () => {
        set({ lang: get().lang === "ru" ? "en" : "ru" });
      },
    }),
    {
      name: "hse-studio-theme",
      partialize: (state) => ({
        theme: state.theme,
        density: state.density,
        lang: state.lang,
      }),
    },
  ),
);
