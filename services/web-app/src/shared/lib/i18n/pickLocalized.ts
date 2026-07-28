/**
 * Selects the right value from a pack/backend `{ ru, en }` label dictionary for
 * the current INTERFACE language, with graceful fallback (interface → ru → en →
 * literal fallback). Use for pack-authored labels surfaced as UI chrome
 * (document type names, check-rule titles, etc.) so they follow the interface
 * language while their underlying document stays on its own `project.lang`.
 */
export const pickLocalized = (
  dict: Partial<Record<string, string>> | undefined,
  lang: string,
  fallback: string,
): string => {
  if (!dict) return fallback;
  return dict[lang] ?? dict.ru ?? dict.en ?? fallback;
};
