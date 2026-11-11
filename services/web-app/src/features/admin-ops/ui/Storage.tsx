import { useState } from "react";
import { RunnerDiskDialog, useRunnerDiskSummary } from "@entities/runner";
import { useServerList } from "@shared/lib";
import { isSweepActive, useLifecycleSweep } from "../api/lifecycleQueries";
import { opsApi } from "../api/opsApi";
import { opsKeys, useStorage } from "../api/opsQueries";
import { listView, useOwnerListState } from "../lib/lists";
import { useNow } from "../lib/useNow";
import { statusOf } from "../lib/viewStatus";
import {
  StorageFreeSpaceDialog,
  type FreeSpaceMode,
} from "./StorageFreeSpaceDialog";
import { StorageView } from "./StorageView";

/**
 * Место: сводка считается на сервере по записям БД, раз в минуту. Владельцы
 * места отдельным списком: поиск, фильтр и порядок на сервере, страницами.
 * «Освободить место» прогоняет ручные очистки «Хранения данных» на сервере, блок
 * «Где ещё» ведёт к срокам и дискам раннеров (docs/design/storage-cleanup.md, 4.3).
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

  const sweepQuery = useLifecycleSweep();
  const sweep = sweepQuery.data ?? null;
  const [dialog, setDialog] = useState<FreeSpaceMode | null>(null);
  const [hiddenSweep, setHiddenSweep] = useState<string | null>(null);

  const summary = useRunnerDiskSummary();
  const [diskRunner, setDiskRunner] = useState<{
    id: string;
    name: string;
  } | null>(null);

  return (
    <>
      <StorageView
        status={statusOf(storage)}
        storage={storage.data ?? null}
        owners={listView(owners, state)}
        now={now}
        onRetry={() => void storage.refetch()}
        freeSpace={{
          sweep: sweep !== null && sweep.id === hiddenSweep ? null : sweep,
          onFreeSpace: () => {
            setDialog(isSweepActive(sweep) ? "sweep" : "preview");
          },
          onDetails: () => {
            setDialog("sweep");
          },
          onHide: (id) => {
            setHiddenSweep(id);
          },
        }}
        moreSpace={{
          status: statusOf(summary),
          summary: summary.data ?? null,
          onRetry: () => void summary.refetch(),
          onOpenRunner: setDiskRunner,
        }}
      />
      <StorageFreeSpaceDialog
        open={dialog !== null}
        mode={dialog ?? "preview"}
        sweep={sweep}
        now={now}
        onClose={() => {
          setDialog(null);
        }}
        onSweepStale={() => void sweepQuery.refetch()}
      />
      <RunnerDiskDialog
        scope="admin"
        runner={diskRunner}
        onClose={() => {
          setDiskRunner(null);
        }}
      />
    </>
  );
};
