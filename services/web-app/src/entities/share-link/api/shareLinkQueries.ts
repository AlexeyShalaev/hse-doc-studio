import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  linkSessionApi,
  shareLinksApi,
  sharingPolicyApi,
} from "./shareLinkApi";
import type {
  CreateShareLinkRequest,
  OpenShareLinkRequest,
  OrgSharingPolicy,
  UpdateAdminSharingRequest,
  UpdateShareLinkRequest,
} from "../model/shareLink.schema";

export const shareLinkKeys = {
  all: ["share-links"] as const,
  project: (projectId: string, includeRevoked: boolean) =>
    [...shareLinkKeys.all, "project", projectId, includeRevoked] as const,
  visits: (projectId: string, linkId: string) =>
    [...shareLinkKeys.all, "visits", projectId, linkId] as const,
  preview: (token: string) => [...shareLinkKeys.all, "preview", token] as const,
  orgPolicy: (slug: string) => [...shareLinkKeys.all, "org", slug] as const,
  adminSettings: () => [...shareLinkKeys.all, "admin"] as const,
};

export const useShareLinks = (
  projectId: string,
  options: { includeRevoked?: boolean; enabled?: boolean } = {},
) =>
  useQuery({
    queryKey: shareLinkKeys.project(projectId, options.includeRevoked ?? false),
    queryFn: () => shareLinksApi.list(projectId, options.includeRevoked),
    enabled: options.enabled ?? true,
    staleTime: 10_000,
  });

const useInvalidateLinks = () => {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: shareLinkKeys.all });
  };
};

export const useCreateShareLink = (projectId: string) => {
  const invalidate = useInvalidateLinks();
  return useMutation({
    mutationFn: (body: CreateShareLinkRequest) =>
      shareLinksApi.create(projectId, body),
    onSuccess: invalidate,
  });
};

export const useUpdateShareLink = (projectId: string) => {
  const invalidate = useInvalidateLinks();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdateShareLinkRequest }) =>
      shareLinksApi.update(projectId, id, body),
    onSuccess: invalidate,
  });
};

export const useRotateShareLink = (projectId: string) => {
  const invalidate = useInvalidateLinks();
  return useMutation({
    mutationFn: (id: string) => shareLinksApi.rotate(projectId, id),
    onSuccess: invalidate,
  });
};

export const useRevokeShareLink = (projectId: string) => {
  const invalidate = useInvalidateLinks();
  return useMutation({
    mutationFn: (id: string) => shareLinksApi.revoke(projectId, id),
    onSuccess: invalidate,
  });
};

export const useShareLinkVisits = (projectId: string, linkId: string | null) =>
  useQuery({
    queryKey: shareLinkKeys.visits(projectId, linkId ?? ""),
    queryFn: () => shareLinksApi.visits(projectId, linkId ?? ""),
    enabled: linkId !== null,
  });

export const useShareLinkPreview = (token: string) =>
  useQuery({
    queryKey: shareLinkKeys.preview(token),
    queryFn: () => linkSessionApi.preview(token),
    retry: false,
    staleTime: 0,
  });

export const useOpenShareLink = (token: string) =>
  useMutation({
    mutationFn: (body: OpenShareLinkRequest) =>
      linkSessionApi.open(token, body),
  });

export const useOrgSharingPolicy = (slug: string, enabled = true) =>
  useQuery({
    queryKey: shareLinkKeys.orgPolicy(slug),
    queryFn: () => sharingPolicyApi.org(slug),
    enabled,
  });

export const useSaveOrgSharingPolicy = (slug: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: OrgSharingPolicy) =>
      sharingPolicyApi.saveOrg(slug, body),
    onSuccess: (saved) => {
      client.setQueryData(shareLinkKeys.orgPolicy(slug), saved);
      void client.invalidateQueries({ queryKey: shareLinkKeys.all });
    },
  });
};

export const useAdminSharingSettings = () =>
  useQuery({
    queryKey: shareLinkKeys.adminSettings(),
    queryFn: () => sharingPolicyApi.admin(),
  });

export const useSaveAdminSharingSettings = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateAdminSharingRequest) =>
      sharingPolicyApi.saveAdmin(body),
    onSuccess: (saved) => {
      client.setQueryData(shareLinkKeys.adminSettings(), saved);
    },
  });
};
