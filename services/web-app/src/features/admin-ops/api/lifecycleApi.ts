import { adminClient, parseResp } from "@shared/api";
import {
  AdminDataLifecycleSchema,
  LifecycleRunSchema,
  LifecycleSweepPreviewSchema,
  LifecycleSweepSchema,
  LifecycleSweepStateSchema,
  type AdminDataLifecycle,
  type LifecycleRun,
  type LifecycleSweep,
  type LifecycleSweepPreview,
  type StorageThresholds,
} from "@entities/session";

// Ошибки форм показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

export const lifecycleApi = {
  overview: (): Promise<AdminDataLifecycle> =>
    adminClient
      .get("/data-lifecycle", quiet)
      .then(parseResp(AdminDataLifecycleSchema)),
  /** `days: null` снимает правку админа: дальше действует умолчание. */
  setRetention: (
    key: string,
    days: number | null,
  ): Promise<AdminDataLifecycle> =>
    adminClient
      .put(`/data-lifecycle/retention/${enc(key)}`, { days }, quiet)
      .then(parseResp(AdminDataLifecycleSchema)),
  setThresholds: (body: StorageThresholds): Promise<AdminDataLifecycle> =>
    adminClient
      .put("/data-lifecycle/thresholds", body, quiet)
      .then(parseResp(AdminDataLifecycleSchema)),
  runNow: (key: string): Promise<LifecycleRun> =>
    adminClient
      .post(`/data-lifecycle/${enc(key)}/run`, {}, quiet)
      .then(parseResp(LifecycleRunSchema)),

  // «Освободить место» (storage-cleanup.md, 9.2): прогон всех ручных источников на сервере.
  /** Что удалится по текущим срокам: счёт с потолком 100 000 по каждому источнику. */
  sweepPreview: (): Promise<LifecycleSweepPreview> =>
    adminClient
      .get("/data-lifecycle/sweep/preview", quiet)
      .then(parseResp(LifecycleSweepPreviewSchema)),
  /** Идущий или последний прогон; null, если прогонов ещё не было. */
  sweep: (): Promise<LifecycleSweep | null> =>
    adminClient
      .get("/data-lifecycle/sweep", quiet)
      .then(parseResp(LifecycleSweepStateSchema))
      .then((state) => state.sweep),
  /** Запустить прогон; второй, пока идёт первый, даёт 409 lifecycle_sweep_busy. */
  startSweep: (): Promise<LifecycleSweep> =>
    adminClient
      .post("/data-lifecycle/sweep", {}, quiet)
      .then(parseResp(LifecycleSweepSchema)),
  /** «Остановить после текущего источника». */
  cancelSweep: (id: string): Promise<LifecycleSweep> =>
    adminClient
      .post(`/data-lifecycle/sweep/${enc(id)}/cancel`, {}, quiet)
      .then(parseResp(LifecycleSweepSchema)),
};
