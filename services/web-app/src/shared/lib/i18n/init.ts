import i18next from "i18next";
import type { Resource, ResourceKey } from "i18next";
import { initReactI18next } from "react-i18next";
import {
  DEFAULT_LANGUAGE,
  DEFAULT_NAMESPACE,
  isSupportedLanguage,
} from "@shared/config";
import type { Lang } from "@shared/api";

declare global {
  // Global augmentation must use `interface` (merges with the lib Window type);
  // a `type` alias cannot. The project's consistent-type-definitions rule is
  // disabled only for this required exception.
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
  interface Window {
    // Set by the inline boot script in index.html BEFORE any module loads, so
    // the very first paint is already in the right language (no RU→EN flash).
    __INITIAL_LANG__?: Lang;
  }
}

// Auto-discover every locale file at `./locales/<lng>/<namespace>.json` and build
// the i18next resources + namespace list from the file tree. Inline + eager (no
// async http-backend) keeps the app local-first and the first render correct.
// Adding a namespace is just dropping a JSON file — no registration needed here.
const localeModules = import.meta.glob("./locales/*/*.json", { eager: true });

const resources: Resource = {};
const namespaces = new Set<string>();
for (const [path, mod] of Object.entries(localeModules)) {
  const match = /\/locales\/([a-z]{2})\/([A-Za-z]+)\.json$/.exec(path);
  if (!match) continue;
  const [, lng, ns] = match;
  if (!lng || !ns) continue;
  const data = (mod as { default: ResourceKey }).default;
  (resources[lng] ??= {})[ns] = data;
  namespaces.add(ns);
}

const resolveBootLanguage = (): Lang => {
  const injected = window.__INITIAL_LANG__;
  return isSupportedLanguage(injected) ? injected : DEFAULT_LANGUAGE;
};

void i18next.use(initReactI18next).init({
  lng: resolveBootLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  ns: [...namespaces],
  defaultNS: DEFAULT_NAMESPACE,
  resources,
  interpolation: { escapeValue: false },
  returnNull: false,
});

export const i18n = i18next;
