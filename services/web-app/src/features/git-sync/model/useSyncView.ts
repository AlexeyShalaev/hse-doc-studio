import { useMemo } from "react";
import { useSyncStatus, type SyncStatusView } from "@entities/git-sync";
import { useProject } from "@entities/project";
import { deriveSyncUi, type SyncUi } from "./syncUi.model";
import { useOnline } from "./useOnline";

export type SyncView = {
  status: SyncStatusView | undefined;
  ui: SyncUi;
  /** Первый ответ ещё не пришёл. */
  isLoading: boolean;
  readOnly: boolean;
  online: boolean;
};

// Состояние синхронизации проекта вместе с готовым описанием, как его показать.
// Запрос один на весь экран (общий ключ), поэтому хук можно вызывать из любого
// числа мест: заголовок, строка состояния, рейка, баннер.
export const useSyncView = (projectId: string): SyncView => {
  const { data: status, isPending } = useSyncStatus(projectId);
  const { data: project } = useProject(projectId);
  const online = useOnline();
  const readOnly = !!project?.access && project.access.mode !== "full";
  const ui = useMemo(
    () => deriveSyncUi(status, { online, readOnly }),
    [status, online, readOnly],
  );
  return {
    status,
    ui,
    isLoading: status === undefined && isPending,
    readOnly,
    online,
  };
};
