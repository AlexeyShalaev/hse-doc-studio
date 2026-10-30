import { adminClient, parseResp } from "@shared/api";
import {
  AdminAuditPageSchema,
  AdminInvitationCreatedSchema,
  AdminInvitationPageSchema,
  AdminResetLinkSchema,
  AdminSessionsRevokedSchema,
  AdminUserPageSchema,
  AdminUserSchema,
  type AccountStatus,
  type AdminAuditPage,
  type AdminInvitationCreated,
  type AdminInvitationPage,
  type AdminResetLink,
  type AdminUser,
  type AdminUserPage,
} from "@entities/session";

// Ошибки действий показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

export const PAGE_SIZE = 25;

export type UsersQuery = {
  q: string;
  status: AccountStatus | "";
  page: number;
};

export type AuditQuery = { action: string; cursor: string | null };

export const adminUsersApi = {
  users: ({ q, status, page }: UsersQuery): Promise<AdminUserPage> =>
    adminClient
      .get("/users", {
        ...quiet,
        params: {
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          ...(q ? { q } : {}),
          ...(status ? { status } : {}),
        },
      })
      .then(parseResp(AdminUserPageSchema)),
  setAdmin: (id: string, isAdmin: boolean): Promise<AdminUser> =>
    adminClient
      .patch(`/users/${enc(id)}`, { is_instance_admin: isAdmin }, quiet)
      .then(parseResp(AdminUserSchema)),
  disable: (id: string): Promise<AdminUser> =>
    adminClient
      .post(`/users/${enc(id)}/disable`, undefined, quiet)
      .then(parseResp(AdminUserSchema)),
  enable: (id: string): Promise<AdminUser> =>
    adminClient
      .post(`/users/${enc(id)}/enable`, undefined, quiet)
      .then(parseResp(AdminUserSchema)),
  remove: async (id: string): Promise<void> => {
    await adminClient.delete(`/users/${enc(id)}`, quiet);
  },
  resetLink: (id: string): Promise<AdminResetLink> =>
    adminClient
      .post(`/users/${enc(id)}/reset-link`, { confirm: true }, quiet)
      .then(parseResp(AdminResetLinkSchema)),
  revokeSessions: (id: string): Promise<number> =>
    adminClient
      .post(`/users/${enc(id)}/sessions/revoke`, undefined, quiet)
      .then(parseResp(AdminSessionsRevokedSchema))
      .then((r) => r.revoked),

  approvals: (page: number): Promise<AdminUserPage> =>
    adminClient
      .get("/approvals", {
        ...quiet,
        params: { limit: PAGE_SIZE, offset: page * PAGE_SIZE },
      })
      .then(parseResp(AdminUserPageSchema)),
  approve: (id: string): Promise<AdminUser> =>
    adminClient
      .post(`/approvals/${enc(id)}/approve`, undefined, quiet)
      .then(parseResp(AdminUserSchema)),
  reject: (id: string): Promise<AdminUser> =>
    adminClient
      .post(`/approvals/${enc(id)}/reject`, undefined, quiet)
      .then(parseResp(AdminUserSchema)),

  invitations: (page: number): Promise<AdminInvitationPage> =>
    adminClient
      .get("/invitations", {
        ...quiet,
        params: { limit: PAGE_SIZE, offset: page * PAGE_SIZE },
      })
      .then(parseResp(AdminInvitationPageSchema)),
  invite: (body: {
    email: string | null;
    ttl_days: number | null;
  }): Promise<AdminInvitationCreated> =>
    adminClient
      .post("/invitations", body, quiet)
      .then(parseResp(AdminInvitationCreatedSchema)),
  resendInvite: (id: string): Promise<AdminInvitationCreated> =>
    adminClient
      .post(`/invitations/${enc(id)}/resend`, undefined, quiet)
      .then(parseResp(AdminInvitationCreatedSchema)),
  revokeInvite: async (id: string): Promise<void> => {
    await adminClient.delete(`/invitations/${enc(id)}`, quiet);
  },

  audit: ({ action, cursor }: AuditQuery): Promise<AdminAuditPage> =>
    adminClient
      .get("/audit", {
        ...quiet,
        params: {
          limit: PAGE_SIZE,
          ...(action ? { action } : {}),
          ...(cursor ? { cursor } : {}),
        },
      })
      .then(parseResp(AdminAuditPageSchema)),
};
