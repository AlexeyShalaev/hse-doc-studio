import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { ListRequestParams } from "@shared/lib";
import type { AccountStatus, AdminUser } from "@entities/session";
import { adminUsersApi } from "./adminUsersApi";

export const adminUsersKeys = {
  all: ["admin", "people"] as const,
  // Только total: сводка, вкладки и меню читают число, а не строки.
  count: (list: "users" | "approvals") =>
    [...adminUsersKeys.all, "count", list] as const,
  // Начала ключей серверных списков: параметры useServerList добавляет сам.
  usersList: () => [...adminUsersKeys.all, "users-list"] as const,
  facets: (q: string) => [...adminUsersKeys.all, "facets", q] as const,
  user: (id: string) => [...adminUsersKeys.all, "user", id] as const,
  approvalsList: () => [...adminUsersKeys.all, "approvals-list"] as const,
  invitationsList: () => [...adminUsersKeys.all, "invitations-list"] as const,
};

/** Сколько людей в установке: total ответа из одной строки, без страницы. */
export const useUserCount = () =>
  useQuery({
    queryKey: adminUsersKeys.count("users"),
    queryFn: ({ signal }) =>
      adminUsersApi.usersPage({ limit: 1, offset: 0 }, signal),
    select: (page) => page.total,
    staleTime: 0,
  });

export const ACCOUNT_STATUSES: readonly AccountStatus[] = [
  "active",
  "pending_verification",
  "pending_approval",
  "disabled",
];

/**
 * Числа на чипах состояний и роли при текущих условиях списка: один запрос.
 * Сервер считает каждый счётчик без его собственного фильтра.
 */
export const useUserFacets = (params: ListRequestParams) =>
  useQuery({
    queryKey: adminUsersKeys.facets(JSON.stringify(params)),
    queryFn: ({ signal }) => adminUsersApi.facets(params, signal),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });

/**
 * Человек для карточки: свежая запись с сервера. Строка страницы служит
 * начальным значением, а карточка не закрывается, когда после действия
 * человек ушёл со страницы (например, отключённый при фильтре «Активные»).
 */
export const useUser = (id: string | null, row: AdminUser | null) =>
  useQuery({
    queryKey: adminUsersKeys.user(id ?? ""),
    queryFn: ({ signal }) => adminUsersApi.user(id ?? "", signal),
    enabled: id !== null,
    staleTime: 0,
    ...(row !== null && row.id === id ? { placeholderData: row } : {}),
  });

/** Сколько ждут одобрения: число для вкладки, сводки и меню. */
export const useApprovalCount = () =>
  useQuery({
    queryKey: adminUsersKeys.count("approvals"),
    queryFn: ({ signal }) =>
      adminUsersApi.approvalsPage({ limit: 1, offset: 0 }, signal),
    select: (page) => page.total,
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

/**
 * Решение по заявке. В пачке (batch) списки не перечитываются после каждой
 * заявки: вызывающий обновляет их один раз в конце через refresh.
 */
export const useDecideApproval = () => {
  const changed = useChanged();
  const mutation = useMutation({
    mutationFn: ({
      id,
      approve,
    }: {
      id: string;
      approve: boolean;
      batch?: boolean;
    }) => (approve ? adminUsersApi.approve(id) : adminUsersApi.reject(id)),
    onSuccess: (_user, { batch = false }) => {
      if (!batch) changed();
    },
  });
  return { ...mutation, refresh: changed };
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
