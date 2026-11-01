import { adminClient, parseResp } from "@shared/api";
import {
  AdminDataLifecycleSchema,
  LifecycleRunSchema,
  type AdminDataLifecycle,
  type LifecycleRun,
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
};
