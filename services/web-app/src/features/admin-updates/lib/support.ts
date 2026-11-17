import type { UpdateRun } from "../api/schemas";
import type { Progress } from "./progress";

const EVENT_TAIL = 12;

/**
 * Текст «Подробности для поддержки»: что за запуск, где остановился и последние строки журнала. Тексты событий
 * очищены сервером от токенов, адресов и путей, здесь ничего не добавляется кроме идентификатора запуска.
 */
export const buildSupportText = (
  run: UpdateRun,
  executor: string,
  appVersion: string,
  progress: Progress,
): string => {
  const head = [
    `run: ${run.id}`,
    `kind: ${run.kind} (${run.trigger})`,
    `status: ${run.status}`,
    `executor: ${executor}`,
    `versions: ${run.from_version} -> ${run.to_version}`,
    `db revision: ${run.from_revision ?? "-"} -> ${run.to_revision ?? "-"}`,
    `db restored: ${run.db_restored ? "yes" : "no"}`,
    `error code: ${run.error_code ?? "-"}`,
    `error: ${run.error ?? "-"}`,
    `stopped at: ${
      progress.steps.find((s) => s.state === "failed")?.id ?? "-"
    }`,
    `created: ${run.created_at}`,
    `finished: ${run.finished_at ?? "-"}`,
    `web app build: ${appVersion}`,
  ];
  const tail = [...run.events]
    .sort((a, b) => a.seq - b.seq)
    .slice(-EVENT_TAIL)
    .map((e) => `${e.at} ${e.level.toUpperCase()} ${e.phase}: ${e.message}`);
  return [...head, "", "last events:", ...tail].join("\n");
};
