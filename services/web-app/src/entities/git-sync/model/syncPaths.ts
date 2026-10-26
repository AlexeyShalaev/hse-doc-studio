// Адреса экранов синхронизации внутри проекта. Лежат в сущности, а не в
// функциях-«ссылках» фич: на них ссылаются сразу несколько фич и виджетов, а
// фичам друг друга импортировать нельзя.

export const gitConflictsPath = (projectId: string): string =>
  `/projects/${projectId}/sync/conflicts`;

export const gitSettingsPath = (projectId: string): string =>
  `/projects/${projectId}/project-settings/sync`;

export const gitHistoryPath = (projectId: string): string =>
  `/projects/${projectId}/versions`;

export const AUTHOR_PROFILE_PATH = "/settings/profile";

// Раздел настроек приложения с токенами, ключами и доверенными серверами.
export const GIT_ACCESS_PATH = "/settings/git-access";

// --- клонирование проекта из git ---------------------------------------------

/** Что передать мастеру клонирования: адрес и сохранённый доступ к нему. */
export type CloneTarget = { url: string; credentialId: string | null };

export const CLONE_PATH = "/wizard?mode=clone";

/** Адрес мастера клонирования; с `target` он откроется с готовым адресом и доступом. */
export const gitClonePath = (target?: CloneTarget | null): string => {
  if (!target) return CLONE_PATH;
  const params = new URLSearchParams({ mode: "clone", url: target.url });
  if (target.credentialId) params.set("credential", target.credentialId);
  return `/wizard?${params.toString()}`;
};

/** Адрес и доступ из строки запроса мастера; null, если адреса в ней нет. */
export const readCloneTarget = (
  params: URLSearchParams,
): CloneTarget | null => {
  const url = params.get("url")?.trim() ?? "";
  if (url === "") return null;
  const credential = params.get("credential")?.trim() ?? "";
  return { url, credentialId: credential === "" ? null : credential };
};
