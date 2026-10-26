import { useNavigate } from "react-router";
import { ConnectRemoteDialog } from "@features/git-remote";
import { SyncControl } from "@features/git-sync";
import { gitClonePath } from "@entities/git-sync";

export type SyncClusterProps = {
  projectId: string;
};

/**
 * Синхронизация проекта в заголовке окна. Виджет собирает то, что относится к
 * ней и живёт в разных фичах: кнопку с панелью состояния (git-sync) и окно
 * подключения репозитория (git-remote). Фичи друг друга не импортируют, поэтому
 * связывает их общее состояние (`useSyncUiStore.connectDialog`): кнопка, палитра
 * команд, настройки и панель синхронизации просят открыть окно, а оно живёт
 * здесь, в одном экземпляре на проект. Страница проекта передаёт виджет в слот
 * `projectActions` заголовка.
 *
 * Если в репозитории лежит другой проект, окно предлагает клонировать его в
 * новую папку: виджет ведёт в мастер клонирования с уже готовым адресом и
 * доступом, фича клонирования сама о подключении ничего не знает.
 */
export const SyncCluster = ({ projectId }: SyncClusterProps) => {
  const navigate = useNavigate();
  return (
    <>
      <SyncControl projectId={projectId} />
      <ConnectRemoteDialog
        projectId={projectId}
        onCloneInstead={(target) => {
          void navigate(gitClonePath(target));
        }}
      />
    </>
  );
};
