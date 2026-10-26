import { useNavigate } from "react-router";
import { ProfilePromptDialog } from "@features/author-profile";
import { BundleExchangeDialog } from "@features/git-exchange";
import { ConnectRemoteDialog } from "@features/git-remote";
import { SyncControl } from "@features/git-sync";
import { gitClonePath, useSyncUiStore } from "@entities/git-sync";

export type SyncClusterProps = {
  projectId: string;
};

/**
 * Синхронизация проекта в заголовке окна. Виджет собирает то, что относится к
 * ней и живёт в разных фичах: кнопку с панелью состояния (git-sync), окно
 * подключения репозитория (git-remote), окно «Представься» (author-profile) и
 * окно обмена файлом (git-exchange). Фичи друг друга не импортируют, поэтому
 * связывает их общее состояние (`useSyncUiStore`): кнопка, палитра команд,
 * настройки и панель синхронизации просят открыть окно, а оно живёт здесь, в
 * одном экземпляре на проект. Страница проекта передаёт виджет в слот
 * `projectActions` заголовка.
 *
 * Если в репозитории лежит другой проект, окно подключения предлагает
 * клонировать его в новую папку: виджет ведёт в мастер клонирования с уже
 * готовым адресом и доступом, фича клонирования сама о подключении ничего не
 * знает.
 */
export const SyncCluster = ({ projectId }: SyncClusterProps) => {
  const navigate = useNavigate();
  const profileOpen = useSyncUiStore((state) => state.profileDialogOpen);
  const closeProfile = useSyncUiStore((state) => state.closeProfileDialog);
  const bundleOpen = useSyncUiStore((state) => state.bundleDialogOpen);
  const closeBundle = useSyncUiStore((state) => state.closeBundleDialog);
  return (
    <>
      <SyncControl projectId={projectId} />
      <ConnectRemoteDialog
        projectId={projectId}
        onCloneInstead={(target) => {
          void navigate(gitClonePath(target));
        }}
      />
      <ProfilePromptDialog
        isOpen={profileOpen}
        reason="sync"
        onClose={closeProfile}
        onSaved={closeProfile}
      />
      <BundleExchangeDialog
        isOpen={bundleOpen}
        projectId={projectId}
        onClose={closeBundle}
      />
    </>
  );
};
