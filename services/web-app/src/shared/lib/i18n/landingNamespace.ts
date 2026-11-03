import { i18n } from "./init";

// Словарь лендинга лежит в подкаталоге landing/, который eager-глоб основного
// бандла не захватывает: его грузит только гость на корне, вместе со страницей.
// Файл landing/landing.json -> пространство `landing` (чанк assets/locale-landing-<lng>-*.js).
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "./locales/*/landing/landing.json",
);

export const LANDING_NS = "landing";

const PATH = /\/locales\/([a-z]{2})\/landing\/landing\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь лендинга (оба языка). Повторный вызов ничего не грузит. */
export const loadLandingNamespace = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng || i18n.hasResourceBundle(lng, LANDING_NS)) return;
      const mod = await load();
      i18n.addResourceBundle(lng, LANDING_NS, mod.default, true, true);
    }),
  ).then(
    () => undefined,
    (error: unknown) => {
      // Провал загрузки не кэшируем: повтор должен пробовать заново.
      pending = null;
      throw error;
    },
  );
  return pending;
};
