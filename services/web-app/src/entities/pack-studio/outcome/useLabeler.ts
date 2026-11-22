import { useMemo } from "react";
import type { OutcomeInput } from "@entities/pack-studio";
import { useInputLabels } from "./useLabels";

export type Labeler = {
  input: (id: string) => string;
  value: (id: string, value: string) => string;
};

export const useLabeler = (
  inputs: readonly OutcomeInput[] | undefined,
): Labeler => {
  const { inputLabel, valueLabel } = useInputLabels();
  return useMemo(() => {
    const byId = new Map((inputs ?? []).map((item) => [item.id, item]));
    return {
      input: (id) => {
        const found = byId.get(id);
        return found ? inputLabel(found) : id;
      },
      value: (id, value) => {
        const found = byId.get(id);
        return found ? valueLabel(found, value) : value;
      },
    };
  }, [inputs, inputLabel, valueLabel]);
};
