import { i18n } from "@shared/lib";

// Словарь раздела лежит в admin/diagnostics.json: чанк админки грузит его вместе с собой,
// тесты грузят только его.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../../shared/lib/i18n/locales/*/admin/diagnostics.json",
);

const PATH = /\/locales\/([a-z]{2})\/admin\/diagnostics\.json$/;

let pending: Promise<void> | null = null;

export const ensureAdminDiagnosticsLocales = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng) return;
      if (i18n.hasResourceBundle(lng, "adminDiagnostics")) return;
      const mod = await load();
      i18n.addResourceBundle(lng, "adminDiagnostics", mod.default, true, true);
    }),
  ).then(() => undefined);
  return pending;
};
