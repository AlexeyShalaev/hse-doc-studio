import i18next from "i18next";

/**
 * BCP-47 locale tag for `Intl` / `toLocale*String` formatting (dates, numbers),
 * derived from the current interface language. Use instead of a hardcoded
 * "ru-RU" so dates/numbers follow the UI language.
 */
export const localeTag = (): string =>
  i18next.language === "en" ? "en-US" : "ru-RU";
