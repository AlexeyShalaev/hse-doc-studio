import { i18n } from "@shared/lib";

// Словарь раздела лежит в admin/backups.json: чанк админки грузит его вместе с собой,
// тесты и галерея грузят только его.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../../shared/lib/i18n/locales/*/admin/backups.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/backups\.json$/;

let pending: Promise<void> | null = null;

export const ensureAdminBackupsLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng) return;
      if (i18n.hasResourceBundle(lng, "adminBackups")) return;
      const mod = await load();
      i18n.addResourceBundle(lng, "adminBackups", mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
