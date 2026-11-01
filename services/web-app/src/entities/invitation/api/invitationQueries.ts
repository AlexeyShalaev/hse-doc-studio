import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { inboxApi, projectInvitationsApi } from "./invitationApi";
import type {
  ApproveAccessRequest,
  CreateProjectInvitationRequest,
  StartProjectTransferRequest,
} from "../model/invitation.schema";

export const invitationKeys = {
  all: ["invitations"] as const,
  project: (projectId: string) =>
    [...invitationKeys.all, "project", projectId] as const,
  invitations: (projectId: string) =>
    [...invitationKeys.project(projectId), "list"] as const,
  requests: (projectId: string) =>
    [...invitationKeys.project(projectId), "requests"] as const,
  transfer: (projectId: string) =>
    [...invitationKeys.project(projectId), "transfer"] as const,
  transferCandidates: (projectId: string, q: string) =>
    [...invitationKeys.project(projectId), "transfer-candidates", q] as const,
  inbox: ["inbox"] as const,
  summary: () => [...invitationKeys.inbox, "summary"] as const,
  notifications: () => [...invitationKeys.inbox, "notifications"] as const,
  mine: () => [...invitationKeys.inbox, "invitations"] as const,
  transfers: () => [...invitationKeys.inbox, "transfers"] as const,
  myRequests: () => [...invitationKeys.inbox, "requests"] as const,
  preview: (token: string) =>
    [...invitationKeys.all, "preview", token] as const,
};

/** Сводку «Входящих» веб перечитывает раз в минуту и при возврате в окно (6.5). */
export const INBOX_POLL_MS = 60_000;

const useInvalidate = () => {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: invitationKeys.all });
};

const useInvalidateInbox = () => {
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: invitationKeys.inbox });
    // Принятое приглашение или передача меняют список проектов и роли.
    await client.invalidateQueries({ queryKey: ["projects"] });
  };
};

// Проект

export const useProjectInvitations = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: invitationKeys.invitations(projectId),
    queryFn: ({ signal }) =>
      projectInvitationsApi.list(projectId, "pending", signal),
    enabled,
    staleTime: 10_000,
  });

export const useProjectAccessRequests = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: invitationKeys.requests(projectId),
    queryFn: ({ signal }) => projectInvitationsApi.requests(projectId, signal),
    enabled,
    staleTime: 10_000,
  });

export const useCreateInvitation = (projectId: string) => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: CreateProjectInvitationRequest) =>
      projectInvitationsApi.create(projectId, body),
    onSettled: invalidate,
  });
};

export const useResendInvitation = (projectId: string) => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (invitationId: string) =>
      projectInvitationsApi.resend(projectId, invitationId),
    onSettled: invalidate,
  });
};

export const useRevokeInvitation = (projectId: string) => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (invitationId: string) =>
      projectInvitationsApi.revoke(projectId, invitationId),
    onSettled: invalidate,
  });
};

export const useDecideAccessRequest = (projectId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (
      p:
        | { requestId: string; approve: ApproveAccessRequest }
        | { requestId: string; approve: null },
    ) =>
      p.approve
        ? projectInvitationsApi.approve(projectId, p.requestId, p.approve)
        : projectInvitationsApi.deny(projectId, p.requestId),
    onSettled: async () => {
      await client.invalidateQueries({ queryKey: invitationKeys.all });
      await client.invalidateQueries({ queryKey: invitationKeys.inbox });
      await client.invalidateQueries({ queryKey: ["project-access"] });
    },
  });
};

export const useProjectTransfer = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: invitationKeys.transfer(projectId),
    queryFn: () => projectInvitationsApi.transfer(projectId),
    enabled,
    staleTime: 10_000,
  });

export const useTransferCandidates = (
  projectId: string,
  q: string,
  enabled: boolean,
) =>
  useQuery({
    queryKey: invitationKeys.transferCandidates(projectId, q),
    queryFn: ({ signal }) =>
      projectInvitationsApi.transferCandidates(projectId, q, signal),
    placeholderData: keepPreviousData,
    enabled,
    staleTime: 5_000,
  });

export const useStartTransfer = (projectId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: StartProjectTransferRequest) =>
      projectInvitationsApi.startTransfer(projectId, body),
    onSettled: async () => {
      await client.invalidateQueries({ queryKey: invitationKeys.all });
      await client.invalidateQueries({ queryKey: ["projects"] });
      await client.invalidateQueries({ queryKey: ["project-access"] });
    },
  });
};

export const useCancelTransfer = (projectId: string) => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => projectInvitationsApi.cancelTransfer(projectId),
    onSettled: invalidate,
  });
};

// «Входящие»

export const useInboxSummary = (enabled = true) =>
  useQuery({
    queryKey: invitationKeys.summary(),
    queryFn: () => inboxApi.summary(),
    enabled,
    refetchInterval: INBOX_POLL_MS,
    refetchOnWindowFocus: true,
    staleTime: 15_000,
  });

export const useNotifications = () =>
  useQuery({
    queryKey: invitationKeys.notifications(),
    queryFn: () => inboxApi.notifications(),
    staleTime: 10_000,
  });

export const useMyInvitations = () =>
  useQuery({
    queryKey: invitationKeys.mine(),
    queryFn: () => inboxApi.invitations(),
    staleTime: 10_000,
  });

export const useMyTransfers = () =>
  useQuery({
    queryKey: invitationKeys.transfers(),
    queryFn: () => inboxApi.transfers(),
    staleTime: 10_000,
  });

export const useMyAccessRequests = () =>
  useQuery({
    queryKey: invitationKeys.myRequests(),
    queryFn: () => inboxApi.myRequests(),
    staleTime: 10_000,
  });

export const useMarkNotificationsRead = () => {
  const invalidate = useInvalidateInbox();
  return useMutation({
    mutationFn: (ids: string[] | null) => inboxApi.markRead(ids),
    onSettled: invalidate,
  });
};

export const useDecideInvitation = () => {
  const invalidate = useInvalidateInbox();
  return useMutation({
    mutationFn: (p: { id: string; accept: boolean }) =>
      p.accept ? inboxApi.accept(p.id) : inboxApi.decline(p.id),
    onSettled: invalidate,
  });
};

export const useDecideTransfer = () => {
  const invalidate = useInvalidateInbox();
  return useMutation({
    mutationFn: (p: { id: string; accept: boolean }) =>
      p.accept ? inboxApi.acceptTransfer(p.id) : inboxApi.declineTransfer(p.id),
    onSettled: invalidate,
  });
};

export const useCancelAccessRequest = () => {
  const invalidate = useInvalidateInbox();
  return useMutation({
    mutationFn: (id: string) => inboxApi.cancelRequest(id),
    onSettled: invalidate,
  });
};

export const useRequestAccess = () =>
  useMutation({
    mutationFn: (p: { projectId: string; message: string | null }) =>
      inboxApi.requestAccess(p.projectId, p.message),
  });

export const useInvitationPreview = (token: string) =>
  useQuery({
    queryKey: invitationKeys.preview(token),
    queryFn: () => inboxApi.preview(token),
    retry: false,
    staleTime: 30_000,
  });

export const useAcceptInvitationByToken = () => {
  const invalidate = useInvalidateInbox();
  return useMutation({
    mutationFn: (token: string) => inboxApi.acceptByToken(token),
    onSettled: invalidate,
  });
};
