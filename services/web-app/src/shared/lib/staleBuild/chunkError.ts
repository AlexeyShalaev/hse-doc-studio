// Ошибки загрузки динамического модуля или CSS-чанка: так браузеры и Vite сообщают, что файла, на который
// ссылается открытая вкладка, на сервере уже нет (вышла новая версия) или он недоступен.

const CHUNK_ERROR_PATTERNS: readonly RegExp[] = [
  /Failed to fetch dynamically imported module/i,
  /error loading dynamically imported module/i,
  /Importing a module script failed/i,
  /Unable to preload CSS/i,
  /Loading (CSS )?chunk [\w-]+ failed/i,
];

const messageOf = (error: unknown): string => {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  if (typeof error === "object" && error !== null && "message" in error) {
    const { message } = error;
    return typeof message === "string" ? message : "";
  }
  return "";
};

export const isChunkLoadError = (error: unknown): boolean => {
  if (error instanceof Error && error.name === "ChunkLoadError") return true;
  const message = messageOf(error);
  return CHUNK_ERROR_PATTERNS.some((pattern) => pattern.test(message));
};
