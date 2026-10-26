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
