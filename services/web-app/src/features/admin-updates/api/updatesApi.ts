import { adminClient, parseResp } from "@shared/api";
import {
  UpdateRunPageSchema,
  UpdateRunSchema,
  UpdateStatusSchema,
  type UpdateRun,
  type UpdateRunPage,
  type UpdateSettings,
  type UpdateStatus,
} from "./schemas";

// Ошибки форм показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;

export const updatesApi = {
  status: (): Promise<UpdateStatus> =>
    adminClient
      .get("/updates/status", quiet)
      .then(parseResp(UpdateStatusSchema)),
  saveSettings: (body: UpdateSettings): Promise<UpdateStatus> =>
    adminClient
      .put("/updates/settings", body, quiet)
      .then(parseResp(UpdateStatusSchema)),
  check: (): Promise<UpdateStatus> =>
    adminClient
      .post("/updates/check", {}, quiet)
      .then(parseResp(UpdateStatusSchema)),
  start: (version: string | null, acceptRisk: boolean): Promise<UpdateRun> =>
    adminClient
      .post("/updates/runs", { version, accept_risk: acceptRisk }, quiet)
      .then(parseResp(UpdateRunSchema)),
  rollback: (restoreDb: boolean): Promise<UpdateRun> =>
    adminClient
      .post("/updates/rollback", { restore_db: restoreDb }, quiet)
      .then(parseResp(UpdateRunSchema)),
  cancel: (id: string): Promise<UpdateRun> =>
    adminClient
      .post(`/updates/runs/${encodeURIComponent(id)}/cancel`, {}, quiet)
      .then(parseResp(UpdateRunSchema)),
  runs: (limit: number, offset: number): Promise<UpdateRunPage> =>
    adminClient
      .get("/updates/runs", { ...quiet, params: { limit, offset } })
      .then(parseResp(UpdateRunPageSchema)),
};
