import { z } from "zod";
import { adminClient, parseResp } from "@shared/api";
import {
  AdminJobPageSchema,
  AdminJobSchema,
  AdminOrgSchema,
  AdminQueueSummarySchema,
  AdminQuotasSchema,
  AdminRunnerRotatedSchema,
  AdminRunnerSchema,
  AdminRunnerTokenCreatedSchema,
  AdminRunnerTokenSchema,
  AdminServiceSchema,
  AdminStorageSchema,
  type AdminJob,
  type AdminJobPage,
  type AdminOrg,
  type AdminQueueSummary,
  type AdminQuotas,
  type AdminRunner,
  type AdminRunnerRotated,
  type AdminRunnerToken,
  type AdminRunnerTokenCreated,
  type AdminService,
  type AdminStorage,
  type CreateAdminRunnerTokenRequest,
  type JobState,
  type UpdateAdminQuotasRequest,
} from "@entities/session";

// Ошибки форм показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

export type QueueQuery = {
  status: JobState | "";
  kind: string;
  q: string;
  limit: number;
};

export const opsApi = {
  runners: (): Promise<AdminRunner[]> =>
    adminClient
      .get("/runners", quiet)
      .then(parseResp(z.array(AdminRunnerSchema))),
  setPaused: async (id: string, paused: boolean): Promise<void> => {
    await adminClient.patch(`/runners/${enc(id)}`, { paused }, quiet);
  },
  rotateToken: (id: string): Promise<AdminRunnerRotated> =>
    adminClient
      .post(`/runners/${enc(id)}/rotate-token`, {}, quiet)
      .then(parseResp(AdminRunnerRotatedSchema)),
  revokeRunner: async (id: string): Promise<void> => {
    await adminClient.delete(`/runners/${enc(id)}`, quiet);
  },

  tokens: (): Promise<AdminRunnerToken[]> =>
    adminClient
      .get("/runner-tokens", quiet)
      .then(parseResp(z.array(AdminRunnerTokenSchema))),
  createToken: (
    body: CreateAdminRunnerTokenRequest,
  ): Promise<AdminRunnerTokenCreated> =>
    adminClient
      .post("/runner-tokens", body, quiet)
      .then(parseResp(AdminRunnerTokenCreatedSchema)),
  revokeToken: async (id: string): Promise<void> => {
    await adminClient.delete(`/runner-tokens/${enc(id)}`, quiet);
  },

  queue: (query: QueueQuery): Promise<AdminJobPage> =>
    adminClient
      .get("/queue", {
        ...quiet,
        params: {
          ...(query.status ? { status: query.status } : {}),
          ...(query.kind ? { kind: query.kind } : {}),
          ...(query.q ? { q: query.q } : {}),
          limit: query.limit,
        },
      })
      .then(parseResp(AdminJobPageSchema)),
  queueSummary: (): Promise<AdminQueueSummary> =>
    adminClient
      .get("/queue/summary", quiet)
      .then(parseResp(AdminQueueSummarySchema)),
  cancelJob: (id: string): Promise<AdminJob> =>
    adminClient
      .post(`/jobs/${enc(id)}/cancel`, {}, quiet)
      .then(parseResp(AdminJobSchema)),

  quotas: (): Promise<AdminQuotas> =>
    adminClient.get("/quotas", quiet).then(parseResp(AdminQuotasSchema)),
  updateQuotas: (body: UpdateAdminQuotasRequest): Promise<AdminQuotas> =>
    adminClient.put("/quotas", body, quiet).then(parseResp(AdminQuotasSchema)),
  setOverride: (
    slug: string,
    body: UpdateAdminQuotasRequest,
  ): Promise<AdminQuotas> =>
    adminClient
      .put(`/quotas/orgs/${enc(slug)}`, body, quiet)
      .then(parseResp(AdminQuotasSchema)),
  clearOverride: (slug: string): Promise<AdminQuotas> =>
    adminClient
      .delete(`/quotas/orgs/${enc(slug)}`, quiet)
      .then(parseResp(AdminQuotasSchema)),
  orgs: (): Promise<AdminOrg[]> =>
    adminClient.get("/orgs", quiet).then(parseResp(z.array(AdminOrgSchema))),

  services: (): Promise<AdminService[]> =>
    adminClient
      .get("/services", quiet)
      .then(parseResp(z.array(AdminServiceSchema))),
  checkService: (id: string): Promise<AdminService> =>
    adminClient
      .post(`/services/${enc(id)}/check`, {}, quiet)
      .then(parseResp(AdminServiceSchema)),

  storage: (): Promise<AdminStorage> =>
    adminClient.get("/storage", quiet).then(parseResp(AdminStorageSchema)),
};
