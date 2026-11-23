import type { ApiToken, TokenScope } from "@entities/session";

/** Права токена в порядке показа: от привычного к редкому. */
export const TOKEN_SCOPES: readonly TokenScope[] = [
  "api",
  "git:read",
  "git:write",
  "mcp",
  "mcp:admin",
  "sign",
  "packs",
];

/** Токен устройства (вход по коду) выдаётся для git и остаётся токеном для git. */
export const DEVICE_SCOPES: readonly TokenScope[] = ["git:read", "git:write"];

/** Права, от которых зависит список инструментов ИИ-клиента (MCP). */
const MCP_SCOPES: readonly TokenScope[] = ["mcp", "mcp:admin", "sign", "packs"];

/**
 * Какие права показать галочками. Сервер то же правило проверяет сам: «MCP: администрирование» только админу,
 * токену устройства только git. Уже выданное право видно всегда, чтобы его можно было снять.
 */
export const offeredScopes = (
  instanceAdmin: boolean,
  token: Pick<ApiToken, "scopes" | "origin"> | null = null,
): TokenScope[] => {
  const base =
    token?.origin === "device"
      ? DEVICE_SCOPES
      : TOKEN_SCOPES.filter((scope) => instanceAdmin || scope !== "mcp:admin");
  const held = token?.scopes ?? [];
  return TOKEN_SCOPES.filter(
    (scope) => base.includes(scope) || held.includes(scope),
  );
};

export type ScopeDiff = { added: TokenScope[]; removed: TokenScope[] };

/** Что добавится и что уберётся, в порядке показа. */
export const scopeDiff = (
  before: readonly TokenScope[],
  after: readonly TokenScope[],
): ScopeDiff => ({
  added: TOKEN_SCOPES.filter((s) => after.includes(s) && !before.includes(s)),
  removed: TOKEN_SCOPES.filter((s) => before.includes(s) && !after.includes(s)),
});

/** Изменение затрагивает инструменты ИИ-клиента: ему нужно переподключиться, чтобы увидеть новый список. */
export const touchesMcp = (diff: ScopeDiff): boolean =>
  [...diff.added, ...diff.removed].some((s) => MCP_SCOPES.includes(s));

/** Срок жизни при создании: дни, null это бессрочный. Больше года сервер не принимает. */
export const TOKEN_EXPIRIES: readonly (number | null)[] = [30, 90, 365, null];
export const DEFAULT_EXPIRY = 90;

/** Ключ словаря для права: git:read становится gitRead, mcp:admin становится mcpAdmin. */
const SCOPE_KEYS: Record<TokenScope, string> = {
  api: "api",
  "git:read": "gitRead",
  "git:write": "gitWrite",
  mcp: "mcp",
  "mcp:admin": "mcpAdmin",
  sign: "sign",
  packs: "packs",
};

export const scopeKey = (scope: TokenScope): string => SCOPE_KEYS[scope];

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
