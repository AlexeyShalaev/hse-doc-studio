import { z } from "zod";
import { adminClient, listPageOf, parseResp } from "@shared/api";
import type { ListPage, ListRequestParams } from "@shared/lib";
import {
  AdminGroupMemberSchema,
  AdminGroupSchema,
  AdminOrgMemberFacetsSchema,
  AdminOrgMemberSchema,
  AdminOrgSchema,
  AdminUserOrgSchema,
  type AdminGroup,
  type AdminGroupMember,
  type AdminOrg,
  type AdminOrgMember,
  type AdminOrgMemberFacets,
  type AdminUserOrg,
  type CreateAdminGroupRequest,
  type CreateAdminOrgRequest,
  type OrgRoleName,
} from "@entities/session";

// Ошибки форм показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

/**
 * Страница списка по единому контракту. Пока сервер не перешёл на Page, он
 * отдаёт весь список массивом: такой ответ показывается одной страницей.
 */
const pageOf = <T extends z.ZodType>(item: T) =>
  z.union([
    listPageOf(item),
    z.array(item).transform((items) => ({
      items,
      total: items.length,
      limit: items.length,
      offset: 0,
    })),
  ]);

const getPage = <T extends z.ZodType>(
  path: string,
  item: T,
  params: ListRequestParams,
  signal: AbortSignal,
): Promise<ListPage<z.infer<T>>> =>
  adminClient
    .get(path, { ...quiet, signal, params })
    .then(parseResp(pageOf(item)));

/** Кого добавить в организацию: найденного в пикере или по почте. */
export type AddMemberInput =
  { userId: string; role: OrgRoleName } | { email: string; role: OrgRoleName };

export const adminOrgsApi = {
  list: (
    params: ListRequestParams,
    signal: AbortSignal,
  ): Promise<ListPage<AdminOrg>> =>
    getPage("/orgs", AdminOrgSchema, params, signal),
  get: (slug: string): Promise<AdminOrg> =>
    adminClient
      .get(`/orgs/${enc(slug)}`, quiet)
      .then(parseResp(AdminOrgSchema)),
  create: (body: CreateAdminOrgRequest): Promise<AdminOrg> =>
    adminClient.post("/orgs", body, quiet).then(parseResp(AdminOrgSchema)),
  remove: async (slug: string): Promise<void> => {
    await adminClient.delete(`/orgs/${enc(slug)}`, quiet);
  },

  members: (
    slug: string,
    params: ListRequestParams,
    signal: AbortSignal,
  ): Promise<ListPage<AdminOrgMember>> =>
    getPage(`/orgs/${enc(slug)}/members`, AdminOrgMemberSchema, params, signal),
  /** Числа на чипах ролей при том же поиске. */
  memberFacets: (
    slug: string,
    q: string,
    signal: AbortSignal,
  ): Promise<AdminOrgMemberFacets> =>
    adminClient
      .get(`/orgs/${enc(slug)}/members/facets`, {
        ...quiet,
        signal,
        params: q ? { q } : {},
      })
      .then(parseResp(AdminOrgMemberFacetsSchema)),
  addMember: (slug: string, input: AddMemberInput): Promise<AdminOrgMember> =>
    adminClient
      .post(
        `/orgs/${enc(slug)}/members`,
        "userId" in input
          ? { user_id: input.userId, role: input.role }
          : { email: input.email, role: input.role },
        quiet,
      )
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

  groups: (
    slug: string,
    params: ListRequestParams,
    signal: AbortSignal,
  ): Promise<ListPage<AdminGroup>> =>
    getPage(`/orgs/${enc(slug)}/groups`, AdminGroupSchema, params, signal),
  createGroup: (
    slug: string,
    body: CreateAdminGroupRequest,
  ): Promise<AdminGroup> =>
    adminClient
      .post(`/orgs/${enc(slug)}/groups`, body, quiet)
      .then(parseResp(AdminGroupSchema)),
  /** Только имя: состав меняется по одному человеку. */
  renameGroup: (slug: string, id: string, name: string): Promise<AdminGroup> =>
    adminClient
      .patch(
        `/orgs/${enc(slug)}/groups/${enc(id)}`,
        { name, member_ids: null },
        quiet,
      )
      .then(parseResp(AdminGroupSchema)),
  removeGroup: async (slug: string, id: string): Promise<void> => {
    await adminClient.delete(`/orgs/${enc(slug)}/groups/${enc(id)}`, quiet);
  },
  groupMembers: (
    slug: string,
    id: string,
    params: ListRequestParams,
    signal: AbortSignal,
  ): Promise<ListPage<AdminGroupMember>> =>
    getPage(
      `/orgs/${enc(slug)}/groups/${enc(id)}/members`,
      AdminGroupMemberSchema,
      params,
      signal,
    ),
  addGroupMember: async (
    slug: string,
    id: string,
    userId: string,
  ): Promise<void> => {
    await adminClient.post(
      `/orgs/${enc(slug)}/groups/${enc(id)}/members/${enc(userId)}`,
      undefined,
      quiet,
    );
  },
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

  /** Организации человека одной ручкой, без обхода составов. */
  userOrgs: (
    userId: string,
    params: ListRequestParams,
    signal: AbortSignal,
  ): Promise<ListPage<AdminUserOrg>> =>
    getPage(`/users/${enc(userId)}/orgs`, AdminUserOrgSchema, params, signal),
};
