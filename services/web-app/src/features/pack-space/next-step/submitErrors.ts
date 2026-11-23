import { ApiError } from "@shared/api";

// Отказы сервера, которые отправка разбирает по смыслу (а не показывает как есть). Поля тела
// ошибки лежат в `ApiError.data`; коды из contracts/pack-studio.

const codeOf = (error: unknown): string | null =>
  error instanceof ApiError ? error.code : null;

const textField = (
  data: Record<string, unknown> | null | undefined,
  key: string,
): string | null => {
  const value = data?.[key];
  return typeof value === "string" && value !== "" ? value : null;
};

/** Лицензия и правила вклада официального репозитория. */
export type LicenseInfo = {
  license: string;
  licenseUrl: string | null;
  contributingUrl: string | null;
};

/** license_consent_required: сервер просит согласие с лицензией; иначе `null`. */
export const consentAsked = (error: unknown): LicenseInfo | null => {
  if (codeOf(error) !== "license_consent_required") return null;
  const data = (error as ApiError).data;
  return {
    license: textField(data, "license") ?? "",
    licenseUrl: textField(data, "license_url"),
    contributingUrl: textField(data, "contributing_url"),
  };
};

/**
 * Отказы, которые лечатся доступом к репозиторию: писать нельзя, доступа нет вовсе, токен не подошёл
 * или истёк. Под ними кнопка «Доступ к репозиторию», иначе «Повторить» упирается в то же самое.
 */
const ACCESS_CODES = new Set([
  "push_denied",
  "credentials_missing",
  "auth_failed",
  "forbidden_write",
  "token_expired",
  "sso_required",
]);

/** Нужен доступ к репозиторию (токен или ключ), чтобы отправка прошла. */
export const needsAccess = (error: unknown): boolean => {
  const code = codeOf(error);
  return code !== null && ACCESS_CODES.has(code);
};

/**
 * version_taken при выпуске: номер уже выпущен в основной ветке. Возвращает свободный номер, на
 * который можно перенести правки; `null`, если ошибка другая или номера нет.
 */
export const takenSuggestion = (error: unknown): string | null =>
  codeOf(error) === "version_taken"
    ? textField((error as ApiError).data, "suggested")
    : null;
