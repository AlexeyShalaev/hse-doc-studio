import type { GitCredential } from "@entities/git-remote";
import { i18n } from "@shared/lib/i18n";
import type { ParsedRemoteUrl } from "./parseRemoteUrl";

// Ключ ssh бывает двух видов: ключ пользователя (один на все репозитории сервера)
// и deploy-ключ (один репозиторий). Для сервера это один и тот же вид доступа, а
// различает их только название: «Deploy-ключ: владелец/репозиторий». Название
// проверяем на обоих языках, чтобы ключ, созданный в одной локали, узнавался в другой.

const LOCALES = ["ru", "en"] as const;
const SAMPLE = "\uE000";

const prefixes = (): string[] =>
  LOCALES.map((lng) => {
    const label = i18n.getFixedT(lng, "gitAccess")("ssh.deployLabel", {
      name: SAMPLE,
    });
    return label.split(SAMPLE)[0] ?? "";
  }).filter((prefix) => prefix !== "");

/** «владелец/репозиторий» из адреса; пустая строка, если репозитория в нём нет. */
export const repoPathOf = (url: ParsedRemoteUrl): string =>
  [url.owner, url.repo].filter(Boolean).join("/");

/** Название нового deploy-ключа для репозитория. */
export const deployKeyLabel = (repoPath: string): string =>
  i18n.t("ssh.deployLabel", { ns: "gitAccess", name: repoPath });

export const isDeployKey = (credential: GitCredential): boolean =>
  prefixes().some((prefix) => credential.label.startsWith(prefix));

/** Репозиторий, для которого создан deploy-ключ (из названия), или null. */
export const deployKeyRepo = (credential: GitCredential): string | null => {
  const prefix = prefixes().find((item) => credential.label.startsWith(item));
  if (prefix === undefined) return null;
  const rest = credential.label.slice(prefix.length).trim();
  return rest === "" ? null : rest;
};

/** Ключи пользователя: все ключи сервера, кроме deploy-ключей. */
export const userKeysOf = (keys: GitCredential[]): GitCredential[] =>
  keys.filter((key) => !isDeployKey(key));

/** Deploy-ключи именно этого репозитория: чужой репозиторий такой ключ не примет. */
export const deployKeysOf = (
  keys: GitCredential[],
  repoPath: string,
): GitCredential[] =>
  keys.filter(
    (key) =>
      isDeployKey(key) &&
      deployKeyRepo(key)?.toLowerCase() === repoPath.toLowerCase(),
  );
