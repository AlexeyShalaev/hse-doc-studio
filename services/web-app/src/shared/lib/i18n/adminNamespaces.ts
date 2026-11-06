import { i18n } from "./init";

// Словари админки лежат в подкаталоге admin/, который eager-глоб основного
// бандла не захватывает. Каждый файл admin/<name>.json — отдельный lazy-чанк
// (assets/locale-admin-<name>-<lng>-*.js, имя задаёт vite.config.ts) и
// пространство имён admin<Name>. Раздел грузит только свои пространства.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "./locales/*/admin/*.json",
);

/**
 * Пространства словарей админки (имена файлов в locales/<lng>/admin/).
 * Новый файл словаря обязан попасть сюда: паритет проверяет locales.test.ts.
 */
export const ADMIN_NAMESPACES = [
  "shell",
  "settings",
  "orgs",
  "users",
  "audit",
  "ops",
  "runners",
  "runnerInstall",
  "quotas",
  "services",
  "storage",
  "data",
  "install",
  "backups",
  "updates",
  "diagnostics",
  "mcp",
] as const;

export type AdminNamespace = (typeof ADMIN_NAMESPACES)[number];

const PATH = /\/locales\/([a-z]{2})\/admin\/([A-Za-z]+)\.json$/;

/** Имя пространства i18next для файла admin/<name>.json. */
export const adminNsName = (name: AdminNamespace): string =>
  `admin${name.charAt(0).toUpperCase()}${name.slice(1)}`;

const pending = new Map<AdminNamespace, Promise<void>>();

const loadOne = (name: AdminNamespace): Promise<void> => {
  const cached = pending.get(name);
  if (cached) return cached;
  const ns = adminNsName(name);
  const promise = Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const match = PATH.exec(path);
      if (match?.[2] !== name) return;
      const lng = match[1];
      if (!lng || i18n.hasResourceBundle(lng, ns)) return;
      const mod = await load();
      i18n.addResourceBundle(lng, ns, mod.default, true, true);
    }),
  ).then(
    () => undefined,
    (error: unknown) => {
      // Провал загрузки не кэшируем: повтор должен пробовать заново.
      pending.delete(name);
      throw error;
    },
  );
  pending.set(name, promise);
  return promise;
};

const batches = new Map<string, Promise<void>>();

/**
 * Подключить словари админки (оба языка) для перечисленных пространств.
 * Повторный вызов с тем же набором возвращает тот же промис и ничего не грузит.
 */
export const loadAdminNamespaces = (
  names: readonly AdminNamespace[],
): Promise<void> => {
  const key = [...names].sort().join(",");
  const cached = batches.get(key);
  if (cached) return cached;
  const promise = Promise.all(names.map(loadOne)).then(
    () => undefined,
    (error: unknown) => {
      batches.delete(key);
      throw error;
    },
  );
  batches.set(key, promise);
  return promise;
};
