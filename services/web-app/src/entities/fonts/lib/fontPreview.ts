import { useEffect, useMemo, useRef } from "react";
import { fontsApi } from "../api/fontsApi";

// Cyrillic + Latin + digits sample shown in every font preview.
export const FONT_SAMPLE = "Съешь ещё мягких булок · AaBbCc · АаБбВв · 123";
export const FONT_SAMPLE_SHORT = "АаБбВв · Aa 123";

export const MARKETPLACE_CATEGORIES = [
  "serif",
  "sans-serif",
  "monospace",
  "display",
  "handwriting",
] as const;

export const cssFallback = (category: string): string => {
  if (category === "monospace") return "monospace";
  if (category === "sans-serif") return "sans-serif";
  if (category === "handwriting") return "cursive";
  return "serif";
};

export const catKey = (category: string): string =>
  category === "sans-serif" ? "sansSerif" : category;

export const formatFontSize = (bytes: number): string =>
  bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024)).toString()} KB`;

// Load a set of Google Fonts families browser-side so previews render in the real
// typeface (this only affects the preview, not what gets installed for LaTeX).
// Each family gets its own <link>, injected once and kept — so growing the list
// (e.g. "Load More") only appends new families instead of tearing down and
// re-fetching the whole stylesheet (which would flash already-rendered cards).
export const useGoogleFontsStylesheet = (families: string[]): void => {
  const key = families.join("|");
  const injectedRef = useRef<Set<string>>(new Set());
  const linksRef = useRef<HTMLLinkElement[]>([]);

  useEffect(() => {
    if (!key) return;
    for (const family of key.split("|")) {
      if (!family || injectedRef.current.has(family)) continue;
      injectedRef.current.add(family);
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = `https://fonts.googleapis.com/css2?family=${family.replace(
        / /g,
        "+",
      )}&display=swap`;
      document.head.appendChild(link);
      linksRef.current.push(link);
    }
  }, [key]);

  // Tear down all injected stylesheets only when the component unmounts.
  useEffect(
    () => () => {
      for (const link of linksRef.current) link.remove();
      linksRef.current = [];
      injectedRef.current.clear();
    },
    [],
  );
};

type PreviewFont = {
  name: string;
  size_bytes: number;
};

// Browsers can't render a TrueType Collection via @font-face (no way to pick a
// face from the collection), so we don't attempt a preview for .ttc files.
const canPreview = (name: string): boolean =>
  !name.toLowerCase().endsWith(".ttc");

// @font-face the user's installed fonts (served by the backend) so they can be
// previewed in-app. Returns a map of font filename → a synthetic CSS family name.
// Synthetic names avoid clashing with OS-installed fonts of the same family; the
// `?v=size` cache-buster keeps the preview fresh after a same-name replacement.
export const useInstalledFontFaces = (
  fonts: PreviewFont[],
): Record<string, string> => {
  const key = fonts
    .map((f) => `${f.name}\t${f.size_bytes.toString()}`)
    .join("\n");

  const families = useMemo(() => {
    const map: Record<string, string> = {};
    if (key) {
      key.split("\n").forEach((entry, i) => {
        const name = entry.split("\t")[0] ?? "";
        if (name && canPreview(name)) {
          map[name] = `hsda-installed-${i.toString()}`;
        }
      });
    }
    return map;
  }, [key]);

  useEffect(() => {
    if (!key) return;
    const rules = key
      .split("\n")
      .map((entry, i) => {
        const parts = entry.split("\t");
        const name = parts[0] ?? "";
        const size = parts[1] ?? "";
        if (!name || !canPreview(name)) return "";
        return (
          `@font-face{font-family:'hsda-installed-${i.toString()}';` +
          `src:url('${fontsApi.fileUrl(name, size)}');font-display:swap;}`
        );
      })
      .filter(Boolean)
      .join("\n");
    if (!rules) return;
    const style = document.createElement("style");
    style.textContent = rules;
    document.head.appendChild(style);
    return () => {
      document.head.removeChild(style);
    };
  }, [key]);

  return families;
};
