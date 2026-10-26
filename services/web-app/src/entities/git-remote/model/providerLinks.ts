import type { GitProvider } from "../api/gitRemoteSchemas";
import { PROVIDER_CATALOG, providerSpec } from "./providerCatalog";

// Ссылки на выпуск токена и добавление ключа. Параметры страниц проверены по
// документации (см. providers.json); всё непроверенное остаётся простой ссылкой.
// Кодирование и обрезка совпадают с core/git_sync/providers.py, векторы общие.

export type ProviderLinkKind = "prefilled" | "plain";

export type ProviderLink = {
  kind: ProviderLinkKind;
  url: string;
  /** Токен с широким доступом: интерфейс предупреждает и советует точный. */
  broad: boolean;
};

export type TokenLinks = {
  primary: ProviderLink | null;
  fallback: ProviderLink | null;
};

export type SshLinks = {
  userKeys: ProviderLink | null;
  deployKey: ProviderLink | null;
};

const MAX_EXPIRES_DAYS = 366;
const WEB_BASE = /^https?:\/\/[^\s/?#]+(?:\/[^\s?#]*)?$/;
const PLACEHOLDER = /^\{(\w+)\}$/;
const PERCENT_ESCAPE = /(%[0-9A-Fa-f]{2})/;

/** Строгое кодирование значения параметра: без кодирования остаются только буквы, цифры и -._~. */
export const encodeComponent = (text: string): string =>
  encodeURIComponent(text).replace(
    /[!'()*]/g,
    (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`,
  );

const encodeSegment = (segment: string): string =>
  segment
    .split(PERCENT_ESCAPE)
    .map((part, index) => (index % 2 === 1 ? part : encodeComponent(part)))
    .join("");

/** Однострочный текст для параметра: управляющие символы и переносы заменены пробелом, длина в символах. */
export const cleanText = (text: string, limit: number): string => {
  const spaced = Array.from(text)
    .map((char) => (/[\s\p{C}]/u.test(char) ? " " : char))
    .join("");
  const joined = spaced.split(/\s+/).filter(Boolean).join(" ");
  return Array.from(joined).slice(0, limit).join("").trimEnd();
};

export const defaultTokenName = (project: string | null): string => {
  const { token_name: names } = PROVIDER_CATALOG.defaults;
  const clean = cleanText(project ?? "", 200);
  return clean
    ? names.with_project.replace("{project}", clean)
    : names.without_project;
};

/** Описание токена: назван Studio и дата (YYYY-MM-DD). */
export const defaultTokenDescription = (day: string, lang: string): string => {
  const templates = PROVIDER_CATALOG.defaults.token_description;
  const template = templates[lang] ?? templates.en ?? "";
  return template.replace("{date}", day);
};

const pathOf = (
  owner: string | null | undefined,
  repo: string | null | undefined,
): string | null => {
  if (!owner || !repo) return null;
  return [...owner.split("/"), repo].map(encodeSegment).join("/");
};

const checkedBase = (base: string): string => {
  if (!WEB_BASE.test(base)) {
    throw new Error("webBase must be an http(s) address without query");
  }
  return base.replace(/\/+$/, "");
};

type Template = {
  kind: ProviderLinkKind;
  broad?: boolean;
  path: string;
  query?: readonly { key: string; value: string }[];
};

const render = (
  template: Template | null,
  base: string,
  path: string | null,
  values: Readonly<Record<string, string | null>>,
): ProviderLink | null => {
  if (!template) return null;
  let route = template.path;
  if (route.includes("{path}")) {
    if (path === null) return null;
    route = route.replace("{path}", path);
  }
  const pairs: string[] = [];
  for (const { key, value } of template.query ?? []) {
    const placeholder = PLACEHOLDER.exec(value);
    if (!placeholder) {
      pairs.push(`${key}=${encodeComponent(value)}`);
      continue;
    }
    const data = values[placeholder[1] ?? ""];
    if (data) pairs.push(`${key}=${data}`);
  }
  const query = pairs.length > 0 ? `?${pairs.join("&")}` : "";
  return {
    kind: template.kind,
    url: `${base}${route}${query}`,
    broad: template.broad ?? false,
  };
};

export type TokenLinkInput = {
  webBase: string;
  name: string;
  description: string;
  owner?: string | null;
  repo?: string | null;
  /** В ссылку попадает только там, где у страницы есть такой параметр (1..366). */
  expiresInDays?: number | null;
};

/**
 * Ссылки на выпуск токена: основная и запасная (для старых версий сервера или
 * широкого токена). Имя и описание очищаются и укорачиваются до лимитов
 * провайдера, затем кодируются строго.
 */
export const tokenLinks = (
  provider: GitProvider,
  input: TokenLinkInput,
): TokenLinks => {
  const spec = providerSpec(provider);
  const base = checkedBase(input.webBase);
  const name = cleanText(input.name, spec.limits.name);
  const description = cleanText(input.description, spec.limits.description);
  const owner = input.owner && !input.owner.includes("/") ? input.owner : null;
  const days = input.expiresInDays;
  const values: Record<string, string | null> = {
    name: name ? encodeComponent(name) : null,
    description: description ? encodeComponent(description) : null,
    scopes: spec.permissions.required.map(encodeComponent).join(","),
    target_name: owner ? encodeComponent(owner) : null,
    expires_in:
      days === null || days === undefined
        ? null
        : String(Math.min(Math.max(days, 1), MAX_EXPIRES_DAYS)),
  };
  const path = pathOf(input.owner, input.repo);
  return {
    primary: render(spec.token_links?.primary ?? null, base, path, values),
    fallback: render(spec.token_links?.fallback ?? null, base, path, values),
  };
};

export type SshLinkInput = {
  webBase: string;
  owner?: string | null;
  repo?: string | null;
};

/** Страницы добавления ключа: ключ пользователя и deploy-ключ репозитория. */
export const sshLinks = (
  provider: GitProvider,
  input: SshLinkInput,
): SshLinks => {
  const spec = providerSpec(provider);
  if (!spec.ssh_links) return { userKeys: null, deployKey: null };
  const base = checkedBase(input.webBase);
  const path = pathOf(input.owner, input.repo);
  return {
    userKeys: render(spec.ssh_links.user_keys, base, path, {}),
    deployKey: render(spec.ssh_links.deploy_key, base, path, {}),
  };
};
