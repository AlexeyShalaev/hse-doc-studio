import { i18n } from "@shared/lib";

// Словарь раздела лежит в admin/updates.json: чанк админки грузит его вместе с собой,
// тесты и галерея грузят только его.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../../shared/lib/i18n/locales/*/admin/updates.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/updates\.json$/;

let pending: Promise<void> | null = null;

export const ensureAdminUpdatesLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng) return;
      if (i18n.hasResourceBundle(lng, "adminUpdates")) return;
      const mod = await load();
      i18n.addResourceBundle(lng, "adminUpdates", mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
