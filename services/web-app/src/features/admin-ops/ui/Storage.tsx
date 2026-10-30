import { useServerList } from "@shared/lib";
import { opsApi } from "../api/opsApi";
import { opsKeys, useStorage } from "../api/opsQueries";
import { listView, useOwnerListState } from "../lib/lists";
import { useNow } from "../lib/useNow";
import { statusOf } from "../lib/viewStatus";
import { StorageView } from "./StorageView";

/**
 * Место: сводка считается на сервере по записям БД, раз в минуту. Владельцы
 * места отдельным списком: поиск, фильтр и порядок на сервере, страницами.
 */
export const Storage = () => {
  const storage = useStorage();
  const state = useOwnerListState();
  const owners = useServerList({
    state,
    queryKey: opsKeys.storageOwners,
    fetchPage: (params, signal) => opsApi.storageOwners(params, signal),
  });
  const now = useNow(15000);
  return (
    <StorageView
      status={statusOf(storage)}
      storage={storage.data ?? null}
      owners={listView(owners, state)}
      now={now}
      onRetry={() => void storage.refetch()}
    />
  );
};
