import { i18n } from "./init";

// Словарь страницы подписанта (/sign/:projectId/:routeId) лежит в подкаталоге signing/,
// который eager-глоб основного бандла не захватывает: его грузит только эта страница,
// вместе со своим чанком. Файл signing/signing.json -> пространство `signing`
// (чанк assets/locale-signing-<lng>-*.js).
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "./locales/*/signing/signing.json",
);

export const SIGNING_NS = "signing";

const PATH = /\/locales\/([a-z]{2})\/signing\/signing\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь страницы подписанта (оба языка). Повторный вызов ничего не грузит. */
export const loadSigningNamespace = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng || i18n.hasResourceBundle(lng, SIGNING_NS)) return;
      const mod = await load();
      i18n.addResourceBundle(lng, SIGNING_NS, mod.default, true, true);
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
