import { useEffect } from "react";
import { useThemeStore } from "./themeStore";
import { PREFERS_DARK_QUERY, resolveTheme } from "./resolveTheme";

export const useApplyTheme = (): void => {
  const theme = useThemeStore((state) => state.theme);
  const density = useThemeStore((state) => state.density);

  useEffect(() => {
    document.documentElement.setAttribute("data-density", density);
  }, [density]);

  useEffect(() => {
    const root = document.documentElement;

    // Explicit themes are applied verbatim; only "system" needs live tracking
    // of the OS colour scheme, so we subscribe to the media query for it alone.
    if (theme !== "system") {
      root.setAttribute("data-theme", theme);
      return;
    }

    const media = window.matchMedia(PREFERS_DARK_QUERY);
    const apply = (): void => {
      root.setAttribute("data-theme", resolveTheme("system", media.matches));
    };
    apply();
    media.addEventListener("change", apply);
    return () => {
      media.removeEventListener("change", apply);
    };
  }, [theme]);
};
