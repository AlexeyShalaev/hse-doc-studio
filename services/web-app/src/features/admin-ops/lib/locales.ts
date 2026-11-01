import { i18n } from "@shared/lib";

// Словарь операционных экранов лежит в admin/ops.json: чанк админки грузит его вместе с собой,
// галерея разработчика грузит только его.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../../shared/lib/i18n/locales/*/admin/ops.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/ops\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь (оба языка). Повторные вызовы возвращают тот же промис. */
export const ensureAdminOpsLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng) return;
      if (i18n.hasResourceBundle(lng, "adminOps")) return;
      const mod = await load();
      i18n.addResourceBundle(lng, "adminOps", mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
