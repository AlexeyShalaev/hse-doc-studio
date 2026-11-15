import { i18n } from "./init";

// Словарь Студии шаблонов (/pack-studio) лежит в подкаталоге packStudio/, который
// eager-глоб основного бандла не захватывает: его грузит только охранник раздела,
// вместе с чанком приложения. Файл packStudio/packStudio.json -> пространство
// `packStudio` (чанк assets/locale-packStudio-<lng>-*.js).
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "./locales/*/packStudio/packStudio.json",
);

export const PACK_STUDIO_NS = "packStudio";

const PATH = /\/locales\/([a-z]{2})\/packStudio\/packStudio\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь Студии шаблонов (оба языка). Повторный вызов ничего не грузит. */
export const loadPackStudioNamespace = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng || i18n.hasResourceBundle(lng, PACK_STUDIO_NS)) return;
      const mod = await load();
      i18n.addResourceBundle(lng, PACK_STUDIO_NS, mod.default, true, true);
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
