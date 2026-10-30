import { i18n } from "@shared/lib";

// Словарь настроек установки лежит в admin/install.json: чанк админки грузит его вместе с собой,
// галерея разработчика грузит только его.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../../shared/lib/i18n/locales/*/admin/install.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/install\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь (оба языка). Повторные вызовы возвращают тот же промис. */
export const ensureAdminInstallLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng) return;
      if (i18n.hasResourceBundle(lng, "adminInstall")) return;
      const mod = await load();
      i18n.addResourceBundle(lng, "adminInstall", mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
