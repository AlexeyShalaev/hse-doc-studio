import {
  PROVIDER_CATALOG,
  defaultTokenDescription,
  defaultTokenName,
  sshLinks,
  tokenLinks,
  webBase,
  type GitProvider,
  type SshLinks,
  type TokenLinks,
} from "@entities/git-remote";
import type { ParsedRemoteUrl } from "./parseRemoteUrl";

// Где на сервере выпускают токен и добавляют ключ. Шаблоны ссылок берутся из
// каталога провайдеров (contracts/git-sync/providers.json): подставляются только
// проверенные параметры, всё остальное остаётся простой ссылкой. Тексты шагов
// лежат в переводах (gitAccess:help.*).

export type HelpProvider = GitProvider;

/** Шаги инструкции по токену: ключи help.<провайдер>.token.<шаг>. */
export const TOKEN_STEPS: Record<HelpProvider, readonly string[]> = {
  github: ["open", "repo", "perm", "copy"],
  gitlab: ["open", "scope", "copy"],
  gitea: ["open", "perm", "copy"],
  bitbucket: ["open", "perm", "copy"],
  other: ["create", "copy"],
};

/** Шаги инструкции по deploy-ключу: ключи help.<провайдер>.key.<шаг>. */
export const KEY_STEPS: Record<HelpProvider, readonly string[]> = {
  github: ["open", "paste", "write"],
  gitlab: ["open", "paste", "write"],
  gitea: ["open", "paste", "write"],
  bitbucket: ["open", "paste", "write"],
  other: ["paste", "write"],
};

/** Шаги инструкции по ключу пользователя: ключи help.<провайдер>.userKey.<шаг>. */
export const USER_KEY_STEPS: Record<HelpProvider, readonly string[]> = {
  github: ["open", "paste"],
  gitlab: ["open", "paste"],
  gitea: ["open", "paste"],
  bitbucket: ["open", "paste"],
  other: ["paste"],
};

export type LinkContext = {
  /** Провайдер с учётом выбора человека; по умолчанию тот, что в адресе. */
  provider?: GitProvider;
  /** Путь установки сервера (https://host/gitlab), если он не в корне. */
  subpath?: string;
  /** Название проекта для имени токена. */
  projectName?: string | null;
  /** Язык описания токена. */
  lang?: string;
  /** Сегодняшняя дата YYYY-MM-DD для описания токена. */
  today?: string;
};

// Адрес сайта сервера: у https и http тот же хост и порт, у ssh порт относится к
// ssh, а не к сайту, поэтому его отбрасываем.
const siteBase = (url: ParsedRemoteUrl, subpath = ""): string | null => {
  if (!url.host || url.kind === "file") return null;
  const hasSitePort = url.kind === "https" || url.kind === "http";
  return webBase({
    host: url.host,
    port: hasSitePort ? url.port : null,
    secure: url.kind !== "http",
    subpath,
  });
};

const repoPath = (url: ParsedRemoteUrl): string =>
  [url.owner, url.repo].filter(Boolean).join("/");

const todayIso = (): string => new Date().toISOString().slice(0, 10);

/** Страница сайта репозитория: ссылка «открыть на сервере». */
export const repoWebUrl = (
  url: ParsedRemoteUrl,
  subpath = "",
): string | null => {
  const base = siteBase(url, subpath);
  return base && url.repo ? `${base}/${repoPath(url)}` : null;
};

/** Ссылки на выпуск токена: основная и запасная; null, если адрес без сайта. */
export const tokenLinksFor = (
  url: ParsedRemoteUrl,
  context: LinkContext = {},
): TokenLinks | null => {
  const base = siteBase(url, context.subpath);
  if (!base) return null;
  try {
    return tokenLinks(context.provider ?? url.provider, {
      webBase: base,
      name: defaultTokenName(context.projectName ?? null),
      description: defaultTokenDescription(
        context.today ?? todayIso(),
        context.lang ?? "ru",
      ),
      owner: url.owner,
      repo: url.repo,
      expiresInDays: PROVIDER_CATALOG.defaults.expires_in_days,
    });
  } catch {
    return null;
  }
};

/** Ссылки на страницы ключей: ключ пользователя и deploy-ключ репозитория. */
export const sshLinksFor = (
  url: ParsedRemoteUrl,
  context: LinkContext = {},
): SshLinks | null => {
  const base = siteBase(url, context.subpath);
  if (!base) return null;
  try {
    return sshLinks(context.provider ?? url.provider, {
      webBase: base,
      owner: url.owner,
      repo: url.repo,
    });
  } catch {
    return null;
  }
};

/** Страница выпуска токена для этого сервера. */
export const tokenCreateUrl = (
  url: ParsedRemoteUrl,
  context: LinkContext = {},
): string | null => tokenLinksFor(url, context)?.primary?.url ?? null;

/** Страница добавления ключа к репозиторию (deploy key с правом записи). */
export const deployKeyUrl = (
  url: ParsedRemoteUrl,
  context: LinkContext = {},
): string | null => sshLinksFor(url, context)?.deployKey?.url ?? null;

/** Имя доступа по умолчанию: «GitHub, github.com». */
export const defaultCredentialLabel = (
  providerName: string,
  host: string,
): string =>
  providerName.toLowerCase() === host ? host : `${providerName}, ${host}`;
