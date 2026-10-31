import { failureCode } from "@shared/api";
import { i18n } from "@shared/lib";

/** Текст ошибки по коду ответа: известные коды из errors:code, иначе общий. */
export const linkErrorText = (error: unknown): string => {
  const code = failureCode(error);
  if (code && i18n.exists(`errors:code.${code}`))
    return i18n.t(`errors:code.${code}`);
  return i18n.t("errors:title.generic");
};
