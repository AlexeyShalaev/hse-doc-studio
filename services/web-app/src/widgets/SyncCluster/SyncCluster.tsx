import { ConnectRemoteDialog } from "@features/git-remote";
import { SyncControl } from "@features/git-sync";

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
 * Кнопка «Клонировать в новую папку» в окне появится, когда у приложения будет
 * мастер клонирования: он передаст сюда `onCloneInstead`.
 */
export const SyncCluster = ({ projectId }: SyncClusterProps) => (
  <>
    <SyncControl projectId={projectId} />
    <ConnectRemoteDialog projectId={projectId} />
  </>
);
