import { useStorage } from "../api/opsQueries";
import { useNow } from "../lib/useNow";
import { StorageView } from "./StorageView";

/** Место: считается на сервере по записям БД, раз в минуту. */
export const Storage = () => {
  const storage = useStorage();
  const now = useNow(15000);
  const status = storage.isError
    ? "error"
    : storage.isPending
      ? "loading"
      : "ready";
  return (
    <StorageView
      status={status}
      storage={storage.data ?? null}
      now={now}
      onRetry={() => void storage.refetch()}
    />
  );
};
