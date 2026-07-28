import { useEffect } from "react";
import i18next from "i18next";
import { useThemeStore } from "../theme";

/**
 * Broadcasts the interface language (single source of truth: `useThemeStore.lang`)
 * to i18next and the document element. Mirror of `useApplyTheme`; mount once via
 * the `LanguageBridge` in `app/providers`.
 *
 * Phase 1 will additionally persist the chosen language to backend settings here.
 */
export const useApplyLanguage = (): void => {
  const lang = useThemeStore((state) => state.lang);

  useEffect(() => {
    if (i18next.language !== lang) {
      void i18next.changeLanguage(lang);
    }
    document.documentElement.lang = lang;
  }, [lang]);
};
