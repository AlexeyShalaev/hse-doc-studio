import { i18n } from "./init";

// Словарь форм Студии шаблонов (features/pack-forms) лежит в подкаталоге
// packForms/: его не берёт ни eager-глоб основного бандла, ни словарь раздела.
// Он грузится вместе с чанком форм (assets/locale-packForms-<lng>-*.js).
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "./locales/*/packForms/packForms.json",
);

export const PACK_FORMS_NS = "packForms";

const PATH = /\/locales\/([a-z]{2})\/packForms\/packForms\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь форм (оба языка). Повторный вызов ничего не грузит. */
export const loadPackFormsNamespace = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng || i18n.hasResourceBundle(lng, PACK_FORMS_NS)) return;
      const mod = await load();
      i18n.addResourceBundle(lng, PACK_FORMS_NS, mod.default, true, true);
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
