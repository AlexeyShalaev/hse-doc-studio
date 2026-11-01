import { adminClient, apiClient, parseResp } from "@shared/api";
import {
  AdminAutoscaleStatusSchema,
  AdminGatewayProviderListSchema,
  AdminQuotaOverrideListSchema,
  AdminQuotaOverrideSchema,
  AdminQuotaPolicySchema,
  AdminUsageSummarySchema,
  MyUsageResponseSchema,
  OwnerUsageResponseSchema,
  type AdminAutoscalePolicy,
  type AdminAutoscaleStatus,
  type AdminGatewayProvider,
  type AdminQuotaOverride,
  type AdminQuotaPolicy,
  type AdminUsageSummary,
  type MyUsage,
  type OwnerKind,
  type OwnerUsage,
  type QuotaResource,
  type ResetUsageRequest,
  type SetAdminQuotaOverrideRequest,
} from "../model/quota.schema";

// Ошибки форм показывают сами экраны: общий тост лишний.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

/** Использование квот человеком и организацией (/api/v1/usage). */
export const usageApi = {
  mine: (): Promise<MyUsage> =>
    apiClient.get("/usage", quiet).then(parseResp(MyUsageResponseSchema)),
  org: (slug: string): Promise<OwnerUsage> =>
    apiClient
      .get(`/orgs/${enc(slug)}/usage`, quiet)
      .then(parseResp(OwnerUsageResponseSchema)),
};

/** Квоты, использование, ИИ-шлюз и автомасштабирование в админке (/api/admin). */
export const quotaAdminApi = {
  policy: (): Promise<AdminQuotaPolicy> =>
    adminClient
      .get("/quota-policy", quiet)
      .then(parseResp(AdminQuotaPolicySchema)),
  savePolicy: (body: AdminQuotaPolicy): Promise<AdminQuotaPolicy> =>
    adminClient
      .put("/quota-policy", body, quiet)
      .then(parseResp(AdminQuotaPolicySchema)),
  overrides: (): Promise<AdminQuotaOverride[]> =>
    adminClient
      .get("/quota-overrides", quiet)
      .then(parseResp(AdminQuotaOverrideListSchema)),
  setOverride: (
    body: SetAdminQuotaOverrideRequest,
  ): Promise<AdminQuotaOverride> =>
    adminClient
      .put("/quota-overrides", body, quiet)
      .then(parseResp(AdminQuotaOverrideSchema)),
  deleteOverride: async (
    ownerKind: OwnerKind,
    ownerId: string,
    resource: QuotaResource,
  ): Promise<void> => {
    await adminClient.delete("/quota-overrides", {
      ...quiet,
      params: { owner_kind: ownerKind, owner_id: ownerId, resource },
    });
  },
  ownerUsage: (ownerKind: OwnerKind, ownerId: string): Promise<OwnerUsage> =>
    adminClient
      .get("/usage", {
        ...quiet,
        params: { owner_kind: ownerKind, owner_id: ownerId },
      })
      .then(parseResp(OwnerUsageResponseSchema)),
  summary: (): Promise<AdminUsageSummary> =>
    adminClient
      .get("/usage/summary", quiet)
      .then(parseResp(AdminUsageSummarySchema)),
  resetUsage: async (body: ResetUsageRequest): Promise<void> => {
    await adminClient.post("/usage/reset", body, quiet);
  },
  gateway: (): Promise<AdminGatewayProvider[]> =>
    adminClient
      .get("/ai-gateway", quiet)
      .then(parseResp(AdminGatewayProviderListSchema)),
  autoscale: (): Promise<AdminAutoscaleStatus> =>
    adminClient
      .get("/autoscale", quiet)
      .then(parseResp(AdminAutoscaleStatusSchema)),
  saveAutoscale: (body: AdminAutoscalePolicy): Promise<AdminAutoscaleStatus> =>
    adminClient
      .put("/autoscale", body, quiet)
      .then(parseResp(AdminAutoscaleStatusSchema)),
};
