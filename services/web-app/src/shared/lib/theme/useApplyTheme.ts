import { useEffect } from "react";
import { useThemeStore } from "./themeStore";
import { applyTextScale } from "./textScale";
import { PREFERS_DARK_QUERY, resolveTheme } from "./resolveTheme";

// Цвет строки состояния и адресной строки мобильного браузера повторяет фон шапки темы.
const syncThemeColor = (root: HTMLElement): void => {
  const meta = document.querySelector<HTMLMetaElement>(
    'meta[name="theme-color"]',
  );
  const color = getComputedStyle(root).getPropertyValue("--bg-1").trim();
  if (meta && color) meta.setAttribute("content", color);
};

export const useApplyTheme = (): void => {
  const theme = useThemeStore((state) => state.theme);
  const density = useThemeStore((state) => state.density);
  const textScale = useThemeStore((state) => state.textScale);

  useEffect(() => {
    applyTextScale(document.documentElement, textScale);
  }, [textScale]);

  useEffect(() => {
    document.documentElement.setAttribute("data-density", density);
  }, [density]);

  useEffect(() => {
    const root = document.documentElement;

    // Explicit themes are applied verbatim; only "system" needs live tracking
    // of the OS colour scheme, so we subscribe to the media query for it alone.
    if (theme !== "system") {
      root.setAttribute("data-theme", theme);
      syncThemeColor(root);
      return;
    }

    const media = window.matchMedia(PREFERS_DARK_QUERY);
    const apply = (): void => {
      root.setAttribute("data-theme", resolveTheme("system", media.matches));
      syncThemeColor(root);
    };
    apply();
    media.addEventListener("change", apply);
    return () => {
      media.removeEventListener("change", apply);
    };
  }, [theme]);
};
