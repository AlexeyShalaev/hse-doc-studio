import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";

/**
 * Текст отказа Студии шаблонов: перевод кода из errors:code.* (коды Студии шаблонов
 * и git-синхронизации), иначе текст сервера, иначе общий. `params` подставляются в
 * перевод (limit, path и другие поля тела ошибки).
 */
export const packErrorText = (error: unknown): string => {
  if (error instanceof ApiError) {
    const key = `errors:code.${error.code}`;
    if (i18n.exists(key)) return i18n.t(key, error.data ?? {});
    if (error.status === 0) return i18n.t("errors:message.network");
    return error.detail;
  }
  return i18n.t("errors:message.unknown");
};

/** Текст ошибки карточки пространства ({code, detail}): перевод кода или текст сервера. */
export const workspaceErrorText = (error: {
  code: string;
  detail: string;
}): string => {
  const key = `errors:code.${error.code}`;
  return i18n.exists(key) ? i18n.t(key) : error.detail;
};
