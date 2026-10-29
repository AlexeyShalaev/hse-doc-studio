import { z } from "zod";
import { adminClient, parseResp } from "@shared/api";
import {
  AdminGroupSchema,
  AdminOrgMemberSchema,
  AdminOrgSchema,
  type AdminGroup,
  type AdminOrg,
  type AdminOrgMember,
  type CreateAdminGroupRequest,
  type CreateAdminOrgRequest,
  type OrgRoleName,
  type UpdateAdminGroupRequest,
} from "@entities/session";

// Ошибки форм показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

export const adminOrgsApi = {
  list: (): Promise<AdminOrg[]> =>
    adminClient.get("/orgs", quiet).then(parseResp(z.array(AdminOrgSchema))),
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
      .get(`/orgs/${enc(slug)}/members`, quiet)
      .then(parseResp(z.array(AdminOrgMemberSchema))),
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
      .get(`/orgs/${enc(slug)}/groups`, quiet)
      .then(parseResp(z.array(AdminGroupSchema))),
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
