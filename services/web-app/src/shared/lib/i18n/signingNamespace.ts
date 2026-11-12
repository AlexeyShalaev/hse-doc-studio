import { i18n } from "./init";

// Словарь страницы подписанта (/sign/:projectId/:routeId) лежит в подкаталоге signing/,
// который eager-глоб основного бандла не захватывает: его грузит только эта страница,
// вместе со своим чанком. Файл signing/signing.json -> пространство `signing`
// (чанк assets/locale-signing-<lng>-*.js).
//
// Тексты редких окон (пароль ключа, КриптоПро, формы ключа, «Нарисовать», «Вернуть на
// доработку») лежат рядом в signing/rare.json и дописываются в то же пространство, когда
// такое окно открывают впервые (чанк assets/locale-signingRare-<lng>-*.js).
type Loaders = Record<
  string,
  () => Promise<{ default: Record<string, unknown> }>
>;

const baseLoaders: Loaders = import.meta.glob<{
  default: Record<string, unknown>;
}>("./locales/*/signing/signing.json");

const rareLoaders: Loaders = import.meta.glob<{
  default: Record<string, unknown>;
}>("./locales/*/signing/rare.json");

export const SIGNING_NS = "signing";

const LANG = /\/locales\/([a-z]{2})\/signing\//;

/** Подключить словарь всех языков один раз; провал не кэшируется: повтор пробует заново. */
const once = (
  loaders: Loaders,
  skip: (lng: string) => boolean,
): (() => Promise<void>) => {
  let pending: Promise<void> | null = null;
  return () => {
    pending ??= Promise.all(
      Object.entries(loaders).map(async ([path, load]) => {
        const lng = LANG.exec(path)?.[1];
        if (!lng || skip(lng)) return;
        const mod = await load();
        i18n.addResourceBundle(lng, SIGNING_NS, mod.default, true, true);
      }),
    ).then(
      () => undefined,
      (error: unknown) => {
        pending = null;
        throw error;
      },
    );
    return pending;
  };
};

/** Подключить словарь страницы подписанта (оба языка). Повторный вызов ничего не грузит. */
export const loadSigningNamespace = once(baseLoaders, (lng) =>
  i18n.hasResourceBundle(lng, SIGNING_NS),
);

const loadRare = once(rareLoaders, () => false);

/** Дописать тексты редких окон (оба языка) поверх основного словаря. Повторный вызов ничего не грузит. */
export const loadSigningRareTexts = (): Promise<void> =>
  loadSigningNamespace().then(loadRare);
