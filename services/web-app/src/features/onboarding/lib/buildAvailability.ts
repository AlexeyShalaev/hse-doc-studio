/**
 * Что сказать в итоге онбординга про сборку. Локально собирает сама Студия; на
 * сервере ответ дают живые общие раннеры (`GET /api/v1/build-availability`).
 * Пока ответа нет или запрос упал, честно говорим «неизвестно».
 */
export type BuildAvailability =
  "local" | "available" | "unavailable" | "unknown";

export type RunnerAvailability = {
  cloud: boolean;
  any_runner: boolean;
  tags: readonly string[];
};

export const resolveBuildAvailability = (
  mode: "local" | "server",
  runners?: RunnerAvailability,
): BuildAvailability => {
  if (mode === "local" || runners?.cloud === false) return "local";
  if (runners === undefined) return "unknown";
  return runners.any_runner && runners.tags.includes("tex")
    ? "available"
    : "unavailable";
};
