import { useShallow } from "zustand/react/shallow";
import { useCompileStreamStore } from "./compileStreamStore";

export type ProjectBuildSummary = {
  /** Раннер взял сборку, она идёт (в том числе молчит). */
  running: number;
  /** Задача поставлена, раннер ещё не взял: нормальное ожидание, не зависание. */
  queued: number;
  /** Запущенные сборки, у которых нет вывода дольше порога. */
  stalled: number;
};

/** Сводка по сборкам проекта: очередь и запуск считаются отдельно, тревога только за запущенными. */
export const useProjectBuildSummary = (
  projectId: string,
): ProjectBuildSummary =>
  useCompileStreamStore(
    useShallow((s): ProjectBuildSummary => {
      const prefix = `${projectId}::`;
      const summary = { running: 0, queued: 0, stalled: 0 };
      for (const [k, slot] of Object.entries(s.streams)) {
        if (!k.startsWith(prefix) || slot.status !== "running") continue;
        if (slot.phase === "queued" || slot.wait !== null) {
          summary.queued += 1;
          continue;
        }
        summary.running += 1;
        if (slot.isStalled) summary.stalled += 1;
      }
      return summary;
    }),
  );
