import { useMemo, type ReactNode } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";

/**
 * Прежние компоненты («Сравнить», «Как студент») читают подписи из словаря старого экрана
 * (`packOutcome`). Чтобы человек не видел там внутренних слов, поверх него накладываются подписи
 * из `packSpace` по пути `path` (на копии словаря: старый экран их не видит).
 */
export const WordsOverlay = ({
  path,
  children,
}: {
  path: string;
  children: ReactNode;
}) => {
  const { i18n } = useTranslation("packSpace");
  const lng = i18n.language;
  const forked = useMemo(() => {
    const clone = i18n.cloneInstance({ forkResourceStore: true });
    const words: unknown = i18n.getResource(lng, "packSpace", path);
    if (words !== null && typeof words === "object") {
      clone.addResourceBundle(lng, "packOutcome", words, true, true);
    }
    return clone;
  }, [i18n, lng, path]);
  return <I18nextProvider i18n={forked}>{children}</I18nextProvider>;
};
