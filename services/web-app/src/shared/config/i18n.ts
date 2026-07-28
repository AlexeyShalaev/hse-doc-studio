import type { Lang } from "@shared/api";

/**
 * Interface (UI) language configuration.
 *
 * This is the language of the application CHROME — buttons, labels, toasts,
 * backend response messages and the agent conversation. It is INDEPENDENT from
 * the document/template language (`project.lang`, the `set_language` chat tool):
 * the UI can be English while the document being written is Russian, and vice
 * versa. The runtime source of truth is `useThemeStore.lang`.
 */
export const DEFAULT_LANGUAGE: Lang = "ru";

export const SUPPORTED_LANGUAGES: readonly Lang[] = ["ru", "en"];

// Namespaces are auto-discovered from the locale file tree at i18next init
// (see shared/lib/i18n/init.ts) — adding one is just dropping a JSON file.
export const DEFAULT_NAMESPACE = "common";

export const isSupportedLanguage = (value: unknown): value is Lang =>
  value === "ru" || value === "en";
