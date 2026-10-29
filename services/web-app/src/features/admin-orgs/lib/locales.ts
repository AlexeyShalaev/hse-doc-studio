import { i18n } from "@shared/lib";

// Словарь организаций лежит в admin/, как и остальные словари админки: чанк админки
// грузит его вместе с собой. Галерея разработчика грузит только его.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../../shared/lib/i18n/locales/*/admin/orgs.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/orgs\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь организаций (оба языка). Повторные вызовы возвращают тот же промис. */
export const ensureAdminOrgsLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng) return;
      if (i18n.hasResourceBundle(lng, "adminOrgs")) return;
      const mod = await load();
      i18n.addResourceBundle(lng, "adminOrgs", mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
