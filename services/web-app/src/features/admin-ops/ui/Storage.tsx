import { useMemo } from "react";
import { usePeople, useStorage } from "../api/opsQueries";
import { useNow } from "../lib/useNow";
import { statusOf } from "../lib/viewStatus";
import { StorageView } from "./StorageView";

/** Место: считается на сервере по записям БД, раз в минуту. */
export const Storage = () => {
  const storage = useStorage();
  const now = useNow(15000);
  const owners = storage.data?.owners;
  const ids = useMemo(() => (owners ?? []).map((o) => o.id), [owners]);
  const people = usePeople(ids);
  return (
    <StorageView
      status={statusOf(storage)}
      storage={storage.data ?? null}
      people={people}
      now={now}
      onRetry={() => void storage.refetch()}
    />
  );
};
