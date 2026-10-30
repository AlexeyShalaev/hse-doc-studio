import { z } from "zod";
import { adminClient, parseResp } from "@shared/api";
import {
  AdminBuildSettingsSchema,
  AdminJobPageSchema,
  AdminJobSchema as WireJobSchema,
  AdminQueueSummarySchema,
  AdminQuotasSchema,
  AdminRunnerRotatedSchema,
  AdminRunnerSchema,
  AdminRunnerTokenCreatedSchema,
  AdminRunnerTokenSchema,
  AdminServiceHealthSchema,
  AdminStorageUsageSchema,
  AdminUserSchema,
  type AdminBuildSettings,
  type AdminJob,
  type AdminJobPage,
  type AdminQueueSummary,
  type AdminQuotas,
  type AdminRunner,
  type AdminRunnerRotated,
  type AdminRunnerToken,
  type AdminRunnerTokenCreated,
  type AdminService,
  type AdminStorage,
  type AdminUser,
  type CreateAdminRunnerTokenRequest,
  type JobState,
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

export type QueueQuery = {
  status: JobState | "";
  kind: string;
  /** Поиск по уже загруженным задачам: сервер его не знает. */
  q: string;
  limit: number;
  /** Где исполняется: на общих или на личных раннерах (runner_scope). */
  scope?: "" | "shared" | "personal";
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

  queue: async (query: QueueQuery): Promise<AdminJobPage> => {
    const page = await adminClient
      .get("/queue", {
        ...quiet,
        params: {
          ...(query.status ? { state: query.status } : {}),
          ...(query.kind ? { kind: query.kind } : {}),
          ...(query.scope ? { runner_scope: query.scope } : {}),
          limit: query.limit,
        },
      })
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

  /** Человек по идентификатору: имя и почта для очереди и списка владельцев. */
  person: (id: string): Promise<AdminUser> =>
    adminClient
      .get(`/users/${enc(id)}`, quiet)
      .then(parseResp(AdminUserSchema)),

  /** Настройки сборки установки: здесь нужен только флаг личных раннеров. */
  buildSettings: (): Promise<AdminBuildSettings> =>
    adminClient
      .get("/settings/build", quiet)
      .then(parseResp(AdminBuildSettingsSchema)),

  storage: async (): Promise<AdminStorage> =>
    storageFromWire(
      await adminClient
        .get("/storage", quiet)
        .then(parseResp(AdminStorageUsageSchema)),
    ),
};
