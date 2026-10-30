import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  CreateAdminGroupRequest,
  CreateAdminOrgRequest,
  OrgRoleName,
} from "@entities/session";
import { adminOrgsApi, type AddMemberInput } from "./adminOrgsApi";

// Списки организаций, участников, групп и состава группы листает сервер
// (useServerList): здесь только начала ключей и мутации, которые их сбрасывают.
export const adminOrgsKeys = {
  all: ["admin", "orgs"] as const,
  list: () => ["admin", "orgs-list"] as const,
  org: (slug: string) => [...adminOrgsKeys.all, slug] as const,
  members: (slug: string) => [...adminOrgsKeys.org(slug), "members"] as const,
  memberFacets: (slug: string, q: string) =>
    [...adminOrgsKeys.members(slug), "facets", q] as const,
  groups: (slug: string) => [...adminOrgsKeys.org(slug), "groups"] as const,
  groupMembers: (slug: string, id: string) =>
    [...adminOrgsKeys.groups(slug), id, "members"] as const,
  userOrgs: (userId: string) => ["admin", "user-orgs", userId] as const,
};

export const useOrg = (slug: string) =>
  useQuery({
    queryKey: adminOrgsKeys.org(slug),
    queryFn: () => adminOrgsApi.get(slug),
    staleTime: 0,
    retry: false,
  });

/** Числа на чипах ролей при текущем поиске. */
export const useMemberFacets = (slug: string, q: string) =>
  useQuery({
    queryKey: adminOrgsKeys.memberFacets(slug, q),
    queryFn: ({ signal }) => adminOrgsApi.memberFacets(slug, q, signal),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });

/** Сколько групп в организации: число на вкладке, одна строка ответа. */
export const useGroupCount = (slug: string) =>
  useQuery({
    queryKey: [...adminOrgsKeys.groups(slug), "count"],
    queryFn: ({ signal }) =>
      adminOrgsApi.groups(slug, { limit: 1, offset: 0 }, signal),
    select: (page) => page.total,
    staleTime: 0,
  });

/**
 * После правки устаревают список организаций (числа), шапка организации,
 * её участники и группы; организации людей в карточках тоже.
 */
const useChanged = (slug?: string) => {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: adminOrgsKeys.list() });
    void client.invalidateQueries({ queryKey: ["admin", "user-orgs"] });
    // Пикеры «не в организации» и «участники организации» тоже устарели.
    void client.invalidateQueries({ queryKey: ["admin", "pickers"] });
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
    mutationFn: (input: AddMemberInput) => adminOrgsApi.addMember(slug, input),
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
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: (userId: string) => adminOrgsApi.removeMember(slug, userId),
    // Ушедший человек уходит и из групп: ключ организации сбрасывает и их.
    onSuccess: changed,
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

export const useRenameGroup = (slug: string) => {
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: (input: { id: string; name: string }) =>
      adminOrgsApi.renameGroup(slug, input.id, input.name),
    onSuccess: changed,
  });
};

/** Состав группы меняется по одному человеку: добавить или убрать. */
export const useGroupMembership = (slug: string, groupId: string) => {
  const changed = useChanged(slug);
  return useMutation({
    mutationFn: ({ userId, add }: { userId: string; add: boolean }) =>
      add
        ? adminOrgsApi.addGroupMember(slug, groupId, userId)
        : adminOrgsApi.removeGroupMember(slug, groupId, userId),
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
