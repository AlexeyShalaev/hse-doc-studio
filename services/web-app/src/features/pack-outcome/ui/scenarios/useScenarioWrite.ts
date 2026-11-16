import { useState } from "react";
import {
  useWritePackScenario,
  type PackScenarioEntry,
  type PackVersionRef,
  type WritePackScenario,
} from "@entities/pack-studio";
import { classifyFailure, type ScenarioFailure } from "../../lib/scenarios";

/**
 * Запись сценария с разобранным отказом: окно показывает его плашкой с действием, а не бросает
 * исключение. `submit` отдаёт запись при успехе и `null` при отказе (причина в `failure`).
 */
export const useScenarioWrite = (workspaceId: string, ref: PackVersionRef) => {
  const mutation = useWritePackScenario(workspaceId, ref.pack, ref.template);
  const [failure, setFailure] = useState<ScenarioFailure | null>(null);
  const { mutateAsync } = mutation;
  const submit = (vars: WritePackScenario): Promise<PackScenarioEntry | null> =>
    mutateAsync(vars).then(
      (entry) => {
        setFailure(null);
        return entry;
      },
      (error: unknown) => {
        setFailure(classifyFailure(error));
        return null;
      },
    );
  return {
    submit,
    pending: mutation.isPending,
    failure,
    clear: () => {
      setFailure(null);
    },
  };
};
