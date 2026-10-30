import { adminClient, parseResp } from "@shared/api";
import {
  AdminGroupMemberSchema,
  AdminGroupPageSchema,
  AdminGroupSchema,
  AdminOrgMemberPageSchema,
  AdminOrgMemberSchema,
  AdminOrgPageSchema,
  AdminOrgSchema,
  AdminUserOrgPageSchema,
  type AdminGroup,
  type AdminGroupMember,
  type AdminOrg,
  type AdminOrgMember,
  type AdminUserOrgPage,
  type CreateAdminGroupRequest,
  type CreateAdminOrgRequest,
  type OrgRoleName,
  type UpdateAdminGroupRequest,
} from "@entities/session";

// Ошибки форм показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;
// Сервер листает списки сам. До перевода экранов на постраничный показ берётся одна страница наибольшего размера.
const FIRST_PAGE = { params: { limit: 200 }, ...quiet } as const;

export const adminOrgsApi = {
  list: (): Promise<AdminOrg[]> =>
    adminClient
      .get("/orgs", FIRST_PAGE)
      .then(parseResp(AdminOrgPageSchema))
      .then((page) => page.items),
  get: (slug: string): Promise<AdminOrg> =>
    adminClient
      .get(`/orgs/${enc(slug)}`, quiet)
      .then(parseResp(AdminOrgSchema)),
  create: (body: CreateAdminOrgRequest): Promise<AdminOrg> =>
    adminClient.post("/orgs", body, quiet).then(parseResp(AdminOrgSchema)),
  remove: async (slug: string): Promise<void> => {
    await adminClient.delete(`/orgs/${enc(slug)}`, quiet);
  },

  members: (slug: string): Promise<AdminOrgMember[]> =>
    adminClient
      .get(`/orgs/${enc(slug)}/members`, FIRST_PAGE)
      .then(parseResp(AdminOrgMemberPageSchema))
      .then((page) => page.items),
  addMember: (
    slug: string,
    body: { email: string; role: OrgRoleName },
  ): Promise<AdminOrgMember> =>
    adminClient
      .post(`/orgs/${enc(slug)}/members`, body, quiet)
      .then(parseResp(AdminOrgMemberSchema)),
  setRole: (
    slug: string,
    userId: string,
    role: OrgRoleName,
  ): Promise<AdminOrgMember> =>
    adminClient
      .patch(`/orgs/${enc(slug)}/members/${enc(userId)}`, { role }, quiet)
      .then(parseResp(AdminOrgMemberSchema)),
  removeMember: async (slug: string, userId: string): Promise<void> => {
    await adminClient.delete(
      `/orgs/${enc(slug)}/members/${enc(userId)}`,
      quiet,
    );
  },

  groups: (slug: string): Promise<AdminGroup[]> =>
    adminClient
      .get(`/orgs/${enc(slug)}/groups`, FIRST_PAGE)
      .then(parseResp(AdminGroupPageSchema))
      .then((page) => page.items),
  /** Состав группы меняется точечно: полный список участников не пересылается. */
  addGroupMember: (
    slug: string,
    id: string,
    userId: string,
  ): Promise<AdminGroupMember> =>
    adminClient
      .post(
        `/orgs/${enc(slug)}/groups/${enc(id)}/members/${enc(userId)}`,
        undefined,
        quiet,
      )
      .then(parseResp(AdminGroupMemberSchema)),
  removeGroupMember: async (
    slug: string,
    id: string,
    userId: string,
  ): Promise<void> => {
    await adminClient.delete(
      `/orgs/${enc(slug)}/groups/${enc(id)}/members/${enc(userId)}`,
      quiet,
    );
  },
  /** Организации человека одним запросом (карточка человека). */
  userOrgs: (userId: string): Promise<AdminUserOrgPage> =>
    adminClient
      .get(`/users/${enc(userId)}/orgs`, FIRST_PAGE)
      .then(parseResp(AdminUserOrgPageSchema)),
  createGroup: (
    slug: string,
    body: CreateAdminGroupRequest,
  ): Promise<AdminGroup> =>
    adminClient
      .post(`/orgs/${enc(slug)}/groups`, body, quiet)
      .then(parseResp(AdminGroupSchema)),
  updateGroup: (
    slug: string,
    id: string,
    body: UpdateAdminGroupRequest,
  ): Promise<AdminGroup> =>
    adminClient
      .patch(`/orgs/${enc(slug)}/groups/${enc(id)}`, body, quiet)
      .then(parseResp(AdminGroupSchema)),
  removeGroup: async (slug: string, id: string): Promise<void> => {
    await adminClient.delete(`/orgs/${enc(slug)}/groups/${enc(id)}`, quiet);
  },
};
