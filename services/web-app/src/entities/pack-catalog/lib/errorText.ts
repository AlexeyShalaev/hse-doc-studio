import { ApiError } from "@shared/api";
import { formatFileSize, i18n } from "@shared/lib";
import { BlockerSchema, type Blocker } from "../api/schemas";

// Отказы «Каталогов паков»: тело {detail, code, ...}, поля по коду лежат в ApiError.data.
// Тексты кодов каталога и кодов git-синхронизации (сбои git источника) лежат в
// errors:code.*, как у Студии шаблонов.

const codeOf = (error: unknown): string | null =>
  error instanceof ApiError ? error.code : null;

/** Параметры перевода: предел архива словами («100 МБ»), а не байтами. */
const paramsOf = (error: ApiError): Record<string, unknown> => {
  const data = error.data ?? {};
  const limit = data.limit;
  return typeof limit === "number"
    ? { ...data, limit: formatFileSize(limit) }
    : data;
};

/** Текст отказа: перевод кода, иначе текст сервера, иначе общий. */
export const catalogErrorText = (error: unknown): string => {
  if (error instanceof ApiError) {
    const key = `errors:code.${error.code}`;
    if (i18n.exists(key)) return i18n.t(key, paramsOf(error));
    if (error.status === 0) return i18n.t("errors:message.network");
    return error.detail;
  }
  return i18n.t("errors:message.unknown");
};

/** Ошибка последней проверки источника ({code, detail}): перевод кода или текст сервера. */
export const sourceErrorText = (error: {
  code: string;
  detail: string;
}): string => {
  const key = `errors:code.${error.code}`;
  return i18n.exists(key) ? i18n.t(key) : error.detail;
};

/** Источник изменился после проверки: нужна новая проверка. */
export const isRevisionMoved = (error: unknown): boolean =>
  codeOf(error) === "revision_moved";

/** С источником уже идёт проверка или применение. */
export const isSourceBusy = (error: unknown): boolean =>
  codeOf(error) === "source_busy";

/** plan_blocked: препятствия, из-за которых «Применить» отказал; иначе null. */
export const planBlockers = (error: unknown): Blocker[] | null => {
  if (codeOf(error) !== "plan_blocked") return null;
  const raw = (error as ApiError).data?.blockers;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item: unknown) => {
    const parsed = BlockerSchema.safeParse(item);
    return parsed.success ? [parsed.data] : [];
  });
};
