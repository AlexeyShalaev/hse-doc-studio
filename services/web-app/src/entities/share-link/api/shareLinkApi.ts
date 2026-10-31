import { adminClient, apiClient, parseResp } from "@shared/api";
import {
  AdminSharingSettingsSchema,
  GuestInfoSchema,
  OpenShareLinkResponseSchema,
  OrgSharingPolicySchema,
  ShareLinkListSchema,
  ShareLinkPreviewSchema,
  ShareLinkSchema,
  ShareLinkVisitPageSchema,
  type AdminSharingSettings,
  type CreateShareLinkRequest,
  type GuestInfo,
  type OpenShareLinkRequest,
  type OpenShareLinkResponse,
  type OrgSharingPolicy,
  type ShareLink,
  type ShareLinkList,
  type ShareLinkPreview,
  type ShareLinkVisitPage,
  type UpdateAdminSharingRequest,
  type UpdateShareLinkRequest,
} from "../model/shareLink.schema";

// Ошибки показывают сами экраны (тост по коду или состояние страницы).
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

/** Ссылки проекта: владелец и редактор с правом делиться (/api/v1/projects/{id}/links*). */
export const shareLinksApi = {
  list: (projectId: string, includeRevoked = false): Promise<ShareLinkList> =>
    apiClient
      .get(`/projects/${enc(projectId)}/links`, {
        ...quiet,
        params: includeRevoked ? { include_revoked: true } : {},
      })
      .then(parseResp(ShareLinkListSchema)),
  create: (
    projectId: string,
    body: CreateShareLinkRequest,
  ): Promise<ShareLink> =>
    apiClient
      .post(`/projects/${enc(projectId)}/links`, body, quiet)
      .then(parseResp(ShareLinkSchema)),
  update: (
    projectId: string,
    linkId: string,
    body: UpdateShareLinkRequest,
  ): Promise<ShareLink> =>
    apiClient
      .patch(`/projects/${enc(projectId)}/links/${enc(linkId)}`, body, quiet)
      .then(parseResp(ShareLinkSchema)),
  rotate: (projectId: string, linkId: string): Promise<ShareLink> =>
    apiClient
      .post(
        `/projects/${enc(projectId)}/links/${enc(linkId)}/rotate`,
        {},
        quiet,
      )
      .then(parseResp(ShareLinkSchema)),
  revoke: async (projectId: string, linkId: string): Promise<void> => {
    await apiClient.delete(
      `/projects/${enc(projectId)}/links/${enc(linkId)}`,
      quiet,
    );
  },
  visits: (projectId: string, linkId: string): Promise<ShareLinkVisitPage> =>
    apiClient
      .get(`/projects/${enc(projectId)}/links/${enc(linkId)}/visits`, quiet)
      .then(parseResp(ShareLinkVisitPageSchema)),
};

/** Страница ссылки и гостевая сессия (/api/v1/links/*). */
export const linkSessionApi = {
  preview: (token: string): Promise<ShareLinkPreview> =>
    apiClient
      .get(`/links/${enc(token)}`, quiet)
      .then(parseResp(ShareLinkPreviewSchema)),
  open: (
    token: string,
    body: OpenShareLinkRequest,
  ): Promise<OpenShareLinkResponse> =>
    apiClient
      .post(`/links/${enc(token)}/open`, body, quiet)
      .then(parseResp(OpenShareLinkResponseSchema)),
  rename: (name: string): Promise<GuestInfo> =>
    apiClient
      .patch("/links/session", { name }, quiet)
      .then(parseResp(GuestInfoSchema)),
  leave: async (): Promise<void> => {
    await apiClient.delete("/links/session", quiet);
  },
};

/** Политика общего доступа организации и установки. */
export const sharingPolicyApi = {
  org: (slug: string): Promise<OrgSharingPolicy> =>
    apiClient
      .get(`/orgs/${enc(slug)}/sharing-policy`, quiet)
      .then(parseResp(OrgSharingPolicySchema)),
  saveOrg: (slug: string, body: OrgSharingPolicy): Promise<OrgSharingPolicy> =>
    apiClient
      .put(`/orgs/${enc(slug)}/sharing-policy`, body, quiet)
      .then(parseResp(OrgSharingPolicySchema)),
  admin: (): Promise<AdminSharingSettings> =>
    adminClient
      .get("/settings/sharing", quiet)
      .then(parseResp(AdminSharingSettingsSchema)),
  saveAdmin: (body: UpdateAdminSharingRequest): Promise<AdminSharingSettings> =>
    adminClient
      .put("/settings/sharing", body, quiet)
      .then(parseResp(AdminSharingSettingsSchema)),
};
