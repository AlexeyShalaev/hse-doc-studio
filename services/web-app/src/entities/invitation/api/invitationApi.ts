import { apiClient, parseResp } from "@shared/api";
import { PickerListSchema } from "@entities/session";
import {
  AccessRequestPageSchema,
  AccessRequestViewSchema,
  InboxSummarySchema,
  MyAccessRequestListSchema,
  MyInvitationListSchema,
  MyInvitationSchema,
  MyTransferListSchema,
  MyTransferSchema,
  NotificationPageSchema,
  ProjectInvitationCreatedSchema,
  ProjectInvitationPageSchema,
  ProjectInvitationPreviewSchema,
  ProjectTransferStateSchema,
  type AccessRequestPage,
  type AccessRequestView,
  type ApproveAccessRequest,
  type CreateProjectInvitationRequest,
  type InboxSummary,
  type MyAccessRequest,
  type MyInvitation,
  type MyTransfer,
  type NotificationPage,
  type ProjectInvitationCreated,
  type ProjectInvitationPage,
  type ProjectInvitationPreview,
  type ProjectTransferState,
  type StartProjectTransferRequest,
} from "../model/invitation.schema";

// Ошибки показывают сами экраны (тост по коду или блок с повтором): общий тост клиента лишний.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;
const project = (id: string) => `/projects/${enc(id)}`;

export type TransferCandidate = {
  kind: "user" | "org";
  id: string;
  name: string;
  detail: string | null;
};

/** Приглашения, запросы доступа и передача владения глазами проекта (раздел 8.2). */
export const projectInvitationsApi = {
  list: (
    projectId: string,
    status: "pending" | "all",
    signal?: AbortSignal,
  ): Promise<ProjectInvitationPage> =>
    apiClient
      .get(`${project(projectId)}/invitations`, {
        ...quiet,
        params: { status, limit: 50 },
        ...(signal ? { signal } : {}),
      })
      .then(parseResp(ProjectInvitationPageSchema)),
  create: (
    projectId: string,
    body: CreateProjectInvitationRequest,
  ): Promise<ProjectInvitationCreated> =>
    apiClient
      .post(`${project(projectId)}/invitations`, body, quiet)
      .then(parseResp(ProjectInvitationCreatedSchema)),
  resend: (
    projectId: string,
    invitationId: string,
  ): Promise<ProjectInvitationCreated> =>
    apiClient
      .post(
        `${project(projectId)}/invitations/${enc(invitationId)}/resend`,
        {},
        quiet,
      )
      .then(parseResp(ProjectInvitationCreatedSchema)),
  revoke: async (projectId: string, invitationId: string): Promise<void> => {
    await apiClient.delete(
      `${project(projectId)}/invitations/${enc(invitationId)}`,
      quiet,
    );
  },
  requests: (
    projectId: string,
    signal?: AbortSignal,
  ): Promise<AccessRequestPage> =>
    apiClient
      .get(`${project(projectId)}/access-requests`, {
        ...quiet,
        params: { status: "pending", limit: 50 },
        ...(signal ? { signal } : {}),
      })
      .then(parseResp(AccessRequestPageSchema)),
  approve: (
    projectId: string,
    requestId: string,
    body: ApproveAccessRequest,
  ): Promise<AccessRequestView> =>
    apiClient
      .post(
        `${project(projectId)}/access-requests/${enc(requestId)}/approve`,
        body,
        quiet,
      )
      .then(parseResp(AccessRequestViewSchema)),
  deny: (projectId: string, requestId: string): Promise<AccessRequestView> =>
    apiClient
      .post(
        `${project(projectId)}/access-requests/${enc(requestId)}/deny`,
        { message: null },
        quiet,
      )
      .then(parseResp(AccessRequestViewSchema)),
  transfer: (projectId: string): Promise<ProjectTransferState> =>
    apiClient
      .get(`${project(projectId)}/transfer`, quiet)
      .then(parseResp(ProjectTransferStateSchema)),
  startTransfer: (
    projectId: string,
    body: StartProjectTransferRequest,
  ): Promise<ProjectTransferState> =>
    apiClient
      .post(`${project(projectId)}/transfer`, body, quiet)
      .then(parseResp(ProjectTransferStateSchema)),
  cancelTransfer: async (projectId: string): Promise<void> => {
    await apiClient.delete(`${project(projectId)}/transfer`, quiet);
  },
  transferCandidates: (
    projectId: string,
    q: string,
    signal?: AbortSignal,
  ): Promise<{ items: TransferCandidate[]; has_more: boolean }> =>
    apiClient
      .get(`${project(projectId)}/transfer-candidates`, {
        ...quiet,
        params: { q, limit: 20 },
        ...(signal ? { signal } : {}),
      })
      .then(parseResp(PickerListSchema))
      .then((page) => ({
        items: page.items.map((i) => ({
          kind: i.kind === "org" ? ("org" as const) : ("user" as const),
          id: i.id,
          name: i.name,
          detail: i.detail ?? null,
        })),
        has_more: page.has_more,
      })),
};

/** Адресат и «Входящие» (/account/*, /project-invitations/*, /access-requests). */
export const inboxApi = {
  summary: (): Promise<InboxSummary> =>
    apiClient
      .get("/account/inbox/summary", quiet)
      .then(parseResp(InboxSummarySchema)),
  notifications: (): Promise<NotificationPage> =>
    apiClient
      .get("/account/notifications", { ...quiet, params: { limit: 100 } })
      .then(parseResp(NotificationPageSchema)),
  markRead: async (ids: string[] | null): Promise<void> => {
    await apiClient.post("/account/notifications/read", { ids }, quiet);
  },
  invitations: (): Promise<MyInvitation[]> =>
    apiClient
      .get("/account/invitations", quiet)
      .then(parseResp(MyInvitationListSchema))
      .then((r) => r.items),
  accept: (id: string): Promise<MyInvitation> =>
    apiClient
      .post(`/account/invitations/${enc(id)}/accept`, {}, quiet)
      .then(parseResp(MyInvitationSchema)),
  decline: (id: string): Promise<MyInvitation> =>
    apiClient
      .post(`/account/invitations/${enc(id)}/decline`, {}, quiet)
      .then(parseResp(MyInvitationSchema)),
  transfers: (): Promise<MyTransfer[]> =>
    apiClient
      .get("/account/transfers", quiet)
      .then(parseResp(MyTransferListSchema))
      .then((r) => r.items),
  acceptTransfer: (id: string): Promise<MyTransfer> =>
    apiClient
      .post(`/account/transfers/${enc(id)}/accept`, {}, quiet)
      .then(parseResp(MyTransferSchema)),
  declineTransfer: (id: string): Promise<MyTransfer> =>
    apiClient
      .post(`/account/transfers/${enc(id)}/decline`, {}, quiet)
      .then(parseResp(MyTransferSchema)),
  myRequests: (): Promise<MyAccessRequest[]> =>
    apiClient
      .get("/account/access-requests", quiet)
      .then(parseResp(MyAccessRequestListSchema))
      .then((r) => r.items),
  cancelRequest: async (id: string): Promise<void> => {
    await apiClient.delete(`/account/access-requests/${enc(id)}`, quiet);
  },
  requestAccess: async (
    projectId: string,
    message: string | null,
  ): Promise<void> => {
    await apiClient.post(
      "/access-requests",
      { project_id: projectId, message },
      quiet,
    );
  },
  preview: (token: string): Promise<ProjectInvitationPreview> =>
    apiClient
      .get(`/project-invitations/${enc(token)}`, quiet)
      .then(parseResp(ProjectInvitationPreviewSchema)),
  acceptByToken: (token: string): Promise<MyInvitation> =>
    apiClient
      .post(`/project-invitations/${enc(token)}/accept`, {}, quiet)
      .then(parseResp(MyInvitationSchema)),
};
