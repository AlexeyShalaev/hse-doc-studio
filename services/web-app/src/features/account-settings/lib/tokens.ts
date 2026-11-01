import type { ApiToken, TokenScope } from "@entities/session";

/** Права токена в порядке показа: от привычного к редкому. */
export const TOKEN_SCOPES: readonly TokenScope[] = [
  "api",
  "git:read",
  "git:write",
];

/** Срок жизни при создании: дни, null это бессрочный. Больше года сервер не принимает. */
export const TOKEN_EXPIRIES: readonly (number | null)[] = [30, 90, 365, null];
export const DEFAULT_EXPIRY = 90;

/** Ключ словаря для права: git:read становится gitRead. */
export const scopeKey = (scope: TokenScope): string =>
  scope === "api" ? "api" : scope === "git:read" ? "gitRead" : "gitWrite";

export const isExpired = (token: ApiToken, now: number = Date.now()): boolean =>
  token.expires_at !== null && Date.parse(token.expires_at) <= now;

/** Дата без времени на языке интерфейса. */
export const formatDay = (value: string, language: string): string => {
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return "";
  return new Intl.DateTimeFormat(language, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(at);
};

/** Куда можно уходить при привязке входа: свой адрес или якорь, но не чужой сайт. */
export const isSafeRedirect = (url: string): boolean =>
  (url.startsWith("/") && !url.startsWith("//")) || url.startsWith("#");
