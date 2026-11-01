import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { quotaAdminApi, usageApi } from "./quotaApi";
import type {
  AdminAutoscalePolicy,
  AdminQuotaPolicy,
  OwnerKind,
  QuotaResource,
  ResetUsageRequest,
  SetAdminQuotaOverrideRequest,
} from "../model/quota.schema";

export const quotaKeys = {
  all: ["quota"] as const,
  mine: () => [...quotaKeys.all, "mine"] as const,
  org: (slug: string) => [...quotaKeys.all, "org", slug] as const,
  policy: () => [...quotaKeys.all, "policy"] as const,
  overrides: () => [...quotaKeys.all, "overrides"] as const,
  owner: (kind: OwnerKind, id: string) =>
    [...quotaKeys.all, "owner", kind, id] as const,
  summary: () => [...quotaKeys.all, "summary"] as const,
  gateway: () => [...quotaKeys.all, "gateway"] as const,
  autoscale: () => [...quotaKeys.all, "autoscale"] as const,
};

export const useMyUsage = () =>
  useQuery({
    queryKey: quotaKeys.mine(),
    queryFn: () => usageApi.mine(),
    staleTime: 15_000,
  });

export const useOrgUsage = (slug: string, enabled = true) =>
  useQuery({
    queryKey: quotaKeys.org(slug),
    queryFn: () => usageApi.org(slug),
    staleTime: 15_000,
    enabled,
  });

export const useQuotaPolicy = () =>
  useQuery({
    queryKey: quotaKeys.policy(),
    queryFn: () => quotaAdminApi.policy(),
  });

export const useSaveQuotaPolicy = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: AdminQuotaPolicy) => quotaAdminApi.savePolicy(body),
    onSuccess: (saved) => {
      client.setQueryData(quotaKeys.policy(), saved);
      void client.invalidateQueries({ queryKey: quotaKeys.mine() });
    },
  });
};

export const useQuotaOverrides = () =>
  useQuery({
    queryKey: quotaKeys.overrides(),
    queryFn: () => quotaAdminApi.overrides(),
  });

export const useSetQuotaOverride = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SetAdminQuotaOverrideRequest) =>
      quotaAdminApi.setOverride(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: quotaKeys.all });
    },
  });
};

export const useDeleteQuotaOverride = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      ownerKind: OwnerKind;
      ownerId: string;
      resource: QuotaResource;
    }) =>
      quotaAdminApi.deleteOverride(args.ownerKind, args.ownerId, args.resource),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: quotaKeys.all });
    },
  });
};

export const useOwnerUsage = (
  kind: OwnerKind,
  id: string | null,
  enabled = true,
) =>
  useQuery({
    queryKey: quotaKeys.owner(kind, id ?? ""),
    queryFn: () => quotaAdminApi.ownerUsage(kind, id ?? ""),
    enabled: enabled && id !== null && id !== "",
    retry: false,
  });

export const useUsageSummary = () =>
  useQuery({
    queryKey: quotaKeys.summary(),
    queryFn: () => quotaAdminApi.summary(),
    staleTime: 30_000,
  });

export const useResetUsage = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ResetUsageRequest) => quotaAdminApi.resetUsage(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: quotaKeys.all });
    },
  });
};

export const useGatewayStatus = () =>
  useQuery({
    queryKey: quotaKeys.gateway(),
    queryFn: () => quotaAdminApi.gateway(),
    refetchInterval: 30_000,
  });

export const useAutoscale = () =>
  useQuery({
    queryKey: quotaKeys.autoscale(),
    queryFn: () => quotaAdminApi.autoscale(),
    refetchInterval: 10_000,
  });

export const useSaveAutoscale = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: AdminAutoscalePolicy) =>
      quotaAdminApi.saveAutoscale(body),
    onSuccess: (saved) => {
      client.setQueryData(quotaKeys.autoscale(), saved);
    },
  });
};
