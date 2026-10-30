import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  CreateAdminGroupRequest,
  CreateAdminOrgRequest,
  OrgRoleName,
  UpdateAdminGroupRequest,
} from "@entities/session";
import { adminOrgsApi } from "./adminOrgsApi";

export const adminOrgsKeys = {
  all: ["admin", "orgs"] as const,
  list: () => ["admin", "orgs-list"] as const,
  org: (slug: string) => [...adminOrgsKeys.all, slug] as const,
  members: (slug: string) => [...adminOrgsKeys.org(slug), "members"] as const,
  groups: (slug: string) => [...adminOrgsKeys.org(slug), "groups"] as const,
};

export const useOrgs = () =>
  useQuery({
    queryKey: adminOrgsKeys.list(),
    queryFn: () => adminOrgsApi.list(),
    staleTime: 0,
  });

export const useOrg = (slug: string) =>
  useQuery({
    queryKey: adminOrgsKeys.org(slug),
    queryFn: () => adminOrgsApi.get(slug),
    staleTime: 0,
    retry: false,
  });

export const useMembers = (slug: string) =>
  useQuery({
    queryKey: adminOrgsKeys.members(slug),
    queryFn: () => adminOrgsApi.members(slug),
    staleTime: 0,
  });

export const useGroups = (slug: string) =>
  useQuery({
    queryKey: adminOrgsKeys.groups(slug),
    queryFn: () => adminOrgsApi.groups(slug),
    staleTime: 0,
  });

/** Число людей и групп видно в списке и в шапке организации: после правки они устаревают. */
const useChanged = (slug?: string) => {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: adminOrgsKeys.list() });
    if (slug)
      void client.invalidateQueries({ queryKey: adminOrgsKeys.org(slug) });
  };
};

export const useCreateOrg = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: (body: CreateAdminOrgRequest) => adminOrgsApi.create(body),
    onSuccess: changed,
  });
};

export const useDeleteOrg = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: (slug: string) => adminOrgsApi.remove(slug),
    onSuccess: changed,
  });
};

export const useAddMember = (slug: string) => {
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: (body: { email: string; role: OrgRoleName }) =>
      adminOrgsApi.addMember(slug, body),
    onSuccess: changed,
  });
};

export const useSetRole = (slug: string) => {
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: (input: { userId: string; role: OrgRoleName }) =>
      adminOrgsApi.setRole(slug, input.userId, input.role),
    onSuccess: changed,
  });
};

export const useRemoveMember = (slug: string) => {
  const client = useQueryClient();
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: (userId: string) => adminOrgsApi.removeMember(slug, userId),
    onSuccess: () => {
      // Ушедший человек уходит и из групп.
      void client.invalidateQueries({ queryKey: adminOrgsKeys.groups(slug) });
      changed();
    },
  });
};

export const useCreateGroup = (slug: string) => {
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: (body: CreateAdminGroupRequest) =>
      adminOrgsApi.createGroup(slug, body),
    onSuccess: changed,
  });
};

export const useUpdateGroup = (slug: string) => {
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: (input: { id: string; body: UpdateAdminGroupRequest }) =>
      adminOrgsApi.updateGroup(slug, input.id, input.body),
    onSuccess: changed,
  });
};

export const useDeleteGroup = (slug: string) => {
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: (id: string) => adminOrgsApi.removeGroup(slug, id),
    onSuccess: changed,
  });
};
