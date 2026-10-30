import { i18n } from "@shared/lib";

// Словарь настроек входа лежит в admin/, как и остальные словари админки:
// чанк админки грузит его вместе с собой. Галерея разработчика грузит только
// его, без остальной админки.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../../shared/lib/i18n/locales/*/admin/settings.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/settings\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь настроек входа (оба языка). Повторные вызовы возвращают тот же промис. */
export const ensureAdminSettingsLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng) return;
      if (i18n.hasResourceBundle(lng, "adminSettings")) return;
      const mod = await load();
      i18n.addResourceBundle(lng, "adminSettings", mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
