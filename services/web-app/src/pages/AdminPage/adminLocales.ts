import { i18n } from "@shared/lib";

// Словари админки лежат в подкаталоге admin/, который eager-глоб основного
// бандла не захватывает: они грузятся только вместе с чанком админки.
// Файл admin/<name>.json становится пространством имён admin<Name>.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../shared/lib/i18n/locales/*/admin/*.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/([A-Za-z]+)\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словари админки (оба языка). Повторные вызовы возвращают тот же промис. */
export const loadAdminLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const match = PATH.exec(path);
      const lng = match?.[1];
      const name = match?.[2];
      if (!lng || !name) return;
      const mod = await load();
      const ns = `admin${name.charAt(0).toUpperCase()}${name.slice(1)}`;
      i18n.addResourceBundle(lng, ns, mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
