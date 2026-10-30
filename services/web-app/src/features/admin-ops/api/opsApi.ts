import { z } from "zod";
import { adminClient, parseResp } from "@shared/api";
import type { ListPage, ListRequestParams } from "@shared/lib";
import {
  AdminJobPageSchema,
  AdminJobSchema as WireJobSchema,
  AdminQueueSummarySchema,
  AdminQuotasSchema,
  AdminRunnerPageSchema,
  AdminRunnerRotatedSchema,
  AdminRunnerSummarySchema,
  AdminRunnerTokenCreatedSchema,
  AdminRunnerTokenPageSchema,
  AdminServiceHealthSchema,
  AdminStorageOwnerPageSchema,
  AdminStorageUsageSchema,
  type AdminJob,
  type AdminJobPage,
  type AdminQueueSummary,
  type AdminQuotas,
  type AdminRunner,
  type AdminRunnerRotated,
  type AdminRunnerSummary,
  type AdminRunnerToken,
  type AdminRunnerTokenCreated,
  type AdminService,
  type AdminStorage,
  type AdminStorageOwnerRow,
  type CreateAdminRunnerTokenRequest,
  type UpdateAdminQuotasRequest,
} from "@entities/session";
import {
  jobFromWire,
  jobPageFromWire,
  quotasFromWire,
  serviceFromWire,
  storageFromWire,
  summaryFromWire,
} from "./wire";

// Ошибки форм показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

// Списки ищут, фильтруют, сортируют и листают на сервере (единый контракт
// списков): params собирает состояние списка в адресе, сюда они идут как есть.
const list = (params: ListRequestParams, signal?: AbortSignal) => ({
  ...quiet,
  params,
  ...(signal ? { signal } : {}),
});

export const opsApi = {
  runners: (
    params: ListRequestParams,
    signal?: AbortSignal,
  ): Promise<ListPage<AdminRunner>> =>
    adminClient
      .get("/runners", list(params, signal))
      .then(parseResp(AdminRunnerPageSchema)),
  /** Счётчики раннеров для плиток, вкладки и навигации: без чтения списка. */
  runnerSummary: (): Promise<AdminRunnerSummary> =>
    adminClient
      .get("/runners/summary", quiet)
      .then(parseResp(AdminRunnerSummarySchema)),
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

  tokens: (
    params: ListRequestParams,
    signal?: AbortSignal,
  ): Promise<ListPage<AdminRunnerToken>> =>
    adminClient
      .get("/runner-tokens", list(params, signal))
      .then(parseResp(AdminRunnerTokenPageSchema)),
  createToken: (
    body: CreateAdminRunnerTokenRequest,
  ): Promise<AdminRunnerTokenCreated> =>
    adminClient
      .post("/runner-tokens", body, quiet)
      .then(parseResp(AdminRunnerTokenCreatedSchema)),
  revokeToken: async (id: string): Promise<void> => {
    await adminClient.delete(`/runner-tokens/${enc(id)}`, quiet);
  },

  /** Страница очереди по курсору: новые первыми, имена людей и раннеров в строке. */
  queue: async (
    params: ListRequestParams & { cursor?: string },
    signal?: AbortSignal,
  ): Promise<AdminJobPage> => {
    const page = await adminClient
      .get("/queue", list(params, signal))
      .then(parseResp(AdminJobPageSchema));
    return jobPageFromWire(page, Date.now());
  },
  queueSummary: async (): Promise<AdminQueueSummary> =>
    summaryFromWire(
      await adminClient
        .get("/queue/summary", quiet)
        .then(parseResp(AdminQueueSummarySchema)),
      Date.now(),
    ),
  cancelJob: async (id: string): Promise<AdminJob> =>
    jobFromWire(
      await adminClient
        .post(`/queue/${enc(id)}/cancel`, {}, quiet)
        .then(parseResp(WireJobSchema)),
      Date.now(),
    ),

  quotas: async (): Promise<AdminQuotas> =>
    quotasFromWire(
      await adminClient
        .get("/quotas", quiet)
        .then(parseResp(AdminQuotasSchema)),
    ),
  /** Сервер заменяет квоты целиком, поэтому меняются только присланные поля. */
  updateQuotas: async (
    body: Partial<UpdateAdminQuotasRequest>,
  ): Promise<AdminQuotas> => {
    const current = await adminClient
      .get("/quotas", quiet)
      .then(parseResp(AdminQuotasSchema));
    const saved = await adminClient
      .put(
        "/quotas",
        {
          user_concurrent: current.user_concurrent,
          org_concurrent: current.org_concurrent,
          max_duration_s: current.max_duration_s,
          ...body,
        },
        quiet,
      )
      .then(parseResp(AdminQuotasSchema));
    return quotasFromWire(saved);
  },

  services: async (): Promise<AdminService[]> =>
    (
      await adminClient
        .get("/services", quiet)
        .then(parseResp(z.array(AdminServiceHealthSchema)))
    )
      .map(serviceFromWire)
      .filter((service): service is AdminService => service !== null),

  storage: async (): Promise<AdminStorage> =>
    storageFromWire(
      await adminClient
        .get("/storage", quiet)
        .then(parseResp(AdminStorageUsageSchema)),
    ),
  /** Все владельцы места страницей: люди и организации, имя и почта в строке. */
  storageOwners: (
    params: ListRequestParams,
    signal?: AbortSignal,
  ): Promise<ListPage<AdminStorageOwnerRow>> =>
    adminClient
      .get("/storage/owners", list(params, signal))
      .then(parseResp(AdminStorageOwnerPageSchema)),
};
