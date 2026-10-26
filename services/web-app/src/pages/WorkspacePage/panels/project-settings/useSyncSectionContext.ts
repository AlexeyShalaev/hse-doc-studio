import { useSyncStatus } from "@entities/git-sync";
import type { ProjectSettingsSectionContext } from "./sectionRegistry";

export type SyncSectionContext = Pick<
  ProjectSettingsSectionContext,
  "syncSupported" | "syncConnected" | "hasSharedFolder"
>;

// Условия показа группы «Синхронизация» берутся из состояния репозитория проекта.
// Запрос общий с кнопкой в заголовке окна, поэтому лишней сети это не добавляет.
// Пока ответа нет, группу считаем доступной (см. ProjectSettingsSectionContext).
export const useSyncSectionContext = (
  projectId: string,
): SyncSectionContext => {
  const { data: status } = useSyncStatus(projectId);
  const supported = status?.supported ?? true;
  const connected = status?.connected ?? false;
  return {
    syncSupported: supported,
    syncConnected: supported && connected,
    hasSharedFolder: supported && connected && !!status?.shared_folder,
  };
};
