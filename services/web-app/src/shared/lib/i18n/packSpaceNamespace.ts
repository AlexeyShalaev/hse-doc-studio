import { i18n } from "./init";

// Словарь нового интерфейса Студии шаблонов (docs/design/pack-studio-ux.md, 8.7) лежит в
// подкаталоге packSpace/ каждого языка: по одному JSON на область (shell.json, result.json, ...).
// Ключи области живут под её именем: файл `shell.json` с `{"back": "..."}` даёт
// `t("shell.back")` в пространстве `packSpace`. Файлы области правит только её срез.
// Языковой `index.ts` собирает все JSON языка в один модуль (один чанк на язык).
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "./locales/*/packSpace/index.ts",
);

export const PACK_SPACE_NS = "packSpace";

const PATH = /\/locales\/([a-z]{2})\/packSpace\/index\.ts$/;

let pending: Promise<void> | null = null;

/** Подключить словарь нового интерфейса (оба языка). Повторный вызов ничего не грузит. */
export const loadPackSpaceNamespace = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng || i18n.hasResourceBundle(lng, PACK_SPACE_NS)) return;
      const mod = await load();
      i18n.addResourceBundle(lng, PACK_SPACE_NS, mod.default, true, true);
    }),
  ).then(
    () => undefined,
    (error: unknown) => {
      // Провал загрузки не кэшируем: повтор должен пробовать заново.
      pending = null;
      throw error;
    },
  );
  return pending;
};
