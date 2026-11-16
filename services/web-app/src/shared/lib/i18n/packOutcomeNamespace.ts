import { i18n } from "./init";

// Словарь экрана «Результат» Студии шаблонов (features/pack-outcome) лежит в подкаталоге
// packOutcome/: его не берёт ни eager-глоб основного бандла, ни словарь раздела. Он грузится
// вместе с чанком экрана (assets/locale-packOutcome-<lng>-*.js).
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(
  "./locales/*/packOutcome/packOutcome.json",
);

export const PACK_OUTCOME_NS = "packOutcome";

const PATH = /\/locales\/([a-z]{2})\/packOutcome\/packOutcome\.json$/;

let pending: Promise<void> | null = null;

/** Подключить словарь экрана «Результат» (оба языка). Повторный вызов ничего не грузит. */
export const loadPackOutcomeNamespace = (): Promise<void> => {
  pending ??= Promise.all(
    Object.entries(loaders).map(async ([path, load]) => {
      const lng = PATH.exec(path)?.[1];
      if (!lng || i18n.hasResourceBundle(lng, PACK_OUTCOME_NS)) return;
      const mod = await load();
      i18n.addResourceBundle(lng, PACK_OUTCOME_NS, mod.default, true, true);
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
