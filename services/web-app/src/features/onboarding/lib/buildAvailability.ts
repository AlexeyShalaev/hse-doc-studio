/**
 * Точка расширения: признак доступности облачной сборки (раннеров) приходит в
 * параллельной ветке. Пока его нет, на сервере ответ «неизвестно», и итоговый экран
 * честно предупреждает, что сборка может быть недоступна, без обещаний.
 */
export type BuildAvailability =
  "local" | "available" | "unavailable" | "unknown";

export const resolveBuildAvailability = (
  mode: "local" | "server",
  runnersAvailable?: boolean,
): BuildAvailability => {
  if (mode === "local") return "local";
  if (runnersAvailable === undefined) return "unknown";
  return runnersAvailable ? "available" : "unavailable";
};
