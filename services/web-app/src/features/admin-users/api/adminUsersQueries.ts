import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { adminUsersApi, type UsersQuery } from "./adminUsersApi";

export const adminUsersKeys = {
  all: ["admin", "people"] as const,
  users: (q: UsersQuery) => [...adminUsersKeys.all, "users", q] as const,
  approvals: (page: number) =>
    [...adminUsersKeys.all, "approvals", page] as const,
  invitations: (page: number) =>
    [...adminUsersKeys.all, "invitations", page] as const,
  audit: (action: string) => ["admin", "audit", action] as const,
};

export const useUsers = (query: UsersQuery) =>
  useQuery({
    queryKey: adminUsersKeys.users(query),
    queryFn: () => adminUsersApi.users(query),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });

export const useApprovals = (page: number) =>
  useQuery({
    queryKey: adminUsersKeys.approvals(page),
    queryFn: () => adminUsersApi.approvals(page),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });

export const useInvitations = (page: number) =>
  useQuery({
    queryKey: adminUsersKeys.invitations(page),
    queryFn: () => adminUsersApi.invitations(page),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });

export const useAudit = (action: string) =>
  useInfiniteQuery({
    queryKey: adminUsersKeys.audit(action),
    queryFn: ({ pageParam }) =>
      adminUsersApi.audit({ action, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    staleTime: 0,
  });

/** Любое действие над людьми меняет списки, счётчики и журнал. */
const useChanged = () => {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: adminUsersKeys.all });
    void client.invalidateQueries({ queryKey: ["admin", "audit"] });
  };
};

export const useUserAction = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: async (action: {
      kind: "disable" | "enable" | "grantAdmin" | "revokeAdmin" | "remove";
      id: string;
    }): Promise<void> => {
      switch (action.kind) {
        case "disable":
          await adminUsersApi.disable(action.id);
          return;
        case "enable":
          await adminUsersApi.enable(action.id);
          return;
        case "grantAdmin":
          await adminUsersApi.setAdmin(action.id, true);
          return;
        case "revokeAdmin":
          await adminUsersApi.setAdmin(action.id, false);
          return;
        case "remove":
          await adminUsersApi.remove(action.id);
          return;
      }
    },
    onSuccess: changed,
  });
};

export const useIssueResetLink = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: (id: string) => adminUsersApi.resetLink(id),
    onSuccess: changed,
  });
};

export const useRevokeSessions = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: (id: string) => adminUsersApi.revokeSessions(id),
    onSuccess: changed,
  });
};

export const useDecideApproval = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      approve ? adminUsersApi.approve(id) : adminUsersApi.reject(id),
    onSuccess: changed,
  });
};

export const useInvite = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: (body: { email: string | null; ttl_days: number | null }) =>
      adminUsersApi.invite(body),
    onSuccess: changed,
  });
};

export const useResendInvite = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: (id: string) => adminUsersApi.resendInvite(id),
    onSuccess: changed,
  });
};

export const useRevokeInvite = () => {
  const changed = useChanged();
  return useMutation({
    mutationFn: (id: string) => adminUsersApi.revokeInvite(id),
    onSuccess: changed,
  });
};
