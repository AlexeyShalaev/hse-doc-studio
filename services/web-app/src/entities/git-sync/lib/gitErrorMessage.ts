import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { gitErrorI18nKey } from "../api/gitErrorCodes";
import { readGitError } from "../api/gitSyncApi";

// Текст ошибки синхронизации для пользователя: перевод по коду, а для кода,
// которого у нас нет (новая Студия на сервере), то, что прислал сервер.
export const gitErrorMessage = (
  code: string,
  detail: string,
  params: Record<string, unknown> = {},
): string => {
  const key = gitErrorI18nKey(code);
  if (key !== null && i18n.exists(key)) {
    return i18n.t(key, { ...params, defaultValue: detail });
  }
  return detail;
};

// То же для пойманной ошибки запроса; без разбора возвращает запасной текст.
export const describeGitError = (error: unknown, fallback = ""): string => {
  const body = readGitError(error);
  if (body) return gitErrorMessage(body.code, body.detail, body);
  if (error instanceof ApiError) return error.detail;
  return error instanceof Error && error.message ? error.message : fallback;
};
