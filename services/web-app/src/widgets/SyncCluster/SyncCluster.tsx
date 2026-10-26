import { SyncControl } from "@features/git-sync";

export type SyncClusterProps = {
  projectId: string;
};

/**
 * Синхронизация проекта в заголовке окна. Виджет собирает то, что относится к
 * ней и живёт в разных фичах: кнопку с панелью состояния (git-sync), а окно
 * подключения репозитория (git-remote) добавляется сюда же, потому что фичи не
 * могут импортировать друг друга. Страница проекта передаёт его в слот
 * `projectActions` заголовка.
 */
export const SyncCluster = ({ projectId }: SyncClusterProps) => (
  <SyncControl projectId={projectId} />
);
