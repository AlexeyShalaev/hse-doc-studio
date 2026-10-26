import type { GitProvider } from "@entities/git-remote";
import type { ParsedRemoteUrl } from "./parseRemoteUrl";

// Где на сервере выпускают токен и добавляют ключ. Ссылки ведут на страницы
// настроек самого сервера; тексты шагов лежат в переводах (gitRemote:help.*).

export type HelpProvider = GitProvider;

/** Шаги инструкции по токену: ключи help.<провайдер>.token.<шаг>. */
export const TOKEN_STEPS: Record<HelpProvider, readonly string[]> = {
  github: ["open", "repo", "perm", "copy"],
  gitlab: ["open", "scope", "copy"],
  gitea: ["open", "perm", "copy"],
  bitbucket: ["open", "perm", "copy"],
  other: ["create", "copy"],
};

/** Шаги инструкции по ключу: ключи help.<провайдер>.key.<шаг>. */
export const KEY_STEPS: Record<HelpProvider, readonly string[]> = {
  github: ["open", "paste", "write"],
  gitlab: ["open", "paste", "write"],
  gitea: ["open", "paste", "write"],
  bitbucket: ["open", "paste", "write"],
  other: ["paste", "write"],
};

// Адрес сайта сервера: у https тот же хост и порт, у ssh порт относится к
// ssh, а не к сайту, поэтому его отбрасываем.
const webBase = (url: ParsedRemoteUrl): string | null => {
  if (!url.host || url.kind === "file") return null;
  const port =
    url.kind === "https" && url.port !== null ? `:${String(url.port)}` : "";
  return `https://${url.host}${port}`;
};

const repoPath = (url: ParsedRemoteUrl): string =>
  [url.owner, url.repo].filter(Boolean).join("/");

/** Страница сайта репозитория: ссылка «открыть на сервере». */
export const repoWebUrl = (url: ParsedRemoteUrl): string | null => {
  const base = webBase(url);
  return base && url.repo ? `${base}/${repoPath(url)}` : null;
};

/** Страница выпуска токена для этого сервера. */
export const tokenCreateUrl = (url: ParsedRemoteUrl): string | null => {
  const base = webBase(url);
  if (!base) return null;
  switch (url.provider) {
    case "github":
      return `${base}/settings/personal-access-tokens/new`;
    case "gitlab":
      return `${base}/-/user_settings/personal_access_tokens?name=HSE+Doc+Studio&scopes=write_repository`;
    case "gitea":
      return `${base}/user/settings/applications`;
    case "bitbucket":
      return `${base}/account/settings/app-passwords/`;
    default:
      return null;
  }
};

/** Страница добавления ключа к репозиторию (deploy key с правом записи). */
export const deployKeyUrl = (url: ParsedRemoteUrl): string | null => {
  const base = webBase(url);
  if (!base || !url.repo) return null;
  const path = repoPath(url);
  switch (url.provider) {
    case "github":
      return `${base}/${path}/settings/keys/new`;
    case "gitlab":
      return `${base}/${path}/-/settings/repository`;
    case "gitea":
      return `${base}/${path}/settings/keys`;
    case "bitbucket":
      return `${base}/${path}/admin/access-keys/`;
    default:
      return null;
  }
};

/** Имя доступа по умолчанию: «GitHub, github.com». */
export const defaultCredentialLabel = (
  providerName: string,
  host: string,
): string =>
  providerName.toLowerCase() === host ? host : `${providerName}, ${host}`;
