import { useCallback, useSyncExternalStore } from "react";
import { getLastProjectEdit, subscribeProjectEdits } from "./editActivity";

/** Время последней правки проекта в этом окне (мс) или null; обновляется вместе с сигналом правки. */
export const useProjectLastEdit = (projectId: string): number | null => {
  const subscribe = useCallback(
    (notify: () => void) =>
      subscribeProjectEdits((id) => {
        if (id === projectId) notify();
      }),
    [projectId],
  );
  const snapshot = useCallback(
    () => getLastProjectEdit(projectId),
    [projectId],
  );
  return useSyncExternalStore(subscribe, snapshot, snapshot);
};
