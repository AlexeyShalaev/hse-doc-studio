import { i18n } from "@shared/lib";

// Словарь людей лежит в admin/, как и остальные словари админки: чанк админки
// грузит его вместе с собой. Галерея разработчика и тесты грузят только его.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../../shared/lib/i18n/locales/*/admin/users.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/users\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь людей (оба языка). Повторные вызовы возвращают тот же промис. */
export const ensureAdminUsersLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng) return;
      if (i18n.hasResourceBundle(lng, "adminUsers")) return;
      const mod = await load();
      i18n.addResourceBundle(lng, "adminUsers", mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
