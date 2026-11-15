import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { sessionKeys } from "@entities/session";
import { packStudioApi } from "./packStudioApi";
import type {
  CreatePackStudioGrantRequest,
  CreatePackWorkspaceRequest,
  PackWorkspace,
} from "./schemas";

export const packStudioKeys = {
  all: ["pack-studio"] as const,
  section: () => [...packStudioKeys.all, "section"] as const,
  workspaces: () => [...packStudioKeys.all, "workspaces"] as const,
  workspace: (id: string) => [...packStudioKeys.workspaces(), id] as const,
  tree: (id: string) => [...packStudioKeys.workspace(id), "tree"] as const,
  file: (id: string, path: string) =>
    [...packStudioKeys.workspace(id), "file", path] as const,
  // Проверки зависят от версии файла: новая версия даёт новый запрос.
  lint: (id: string, target: string, revision: string) =>
    [...packStudioKeys.workspace(id), "lint", target, revision] as const,
  hints: (id: string, version: string) =>
    [...packStudioKeys.workspace(id), "hints", version] as const,
  admin: () => [...packStudioKeys.all, "admin"] as const,
};

/** Пока идёт клон или выборка, карточку опрашиваем: фоновая операция без operation_id. */
export const WORKSPACE_POLL_MS = 1500;

const pollWhileBusy = (workspace: PackWorkspace | undefined): number | false =>
  workspace?.busy ? WORKSPACE_POLL_MS : false;

export const usePackStudioSection = (enabled = true) =>
  useQuery({
    queryKey: packStudioKeys.section(),
    queryFn: () => packStudioApi.section(),
    enabled,
  });

/** Переключатель «Инструменты автора шаблонов» локальной Студии; возможность в bootstrap меняется с ним. */
export const useSetPackStudioSection = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => packStudioApi.setSection(enabled),
    onSuccess: (section) => {
      client.setQueryData(packStudioKeys.section(), section);
      void client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });
    },
  });
};

export const usePackWorkspaces = () =>
  useQuery({
    queryKey: packStudioKeys.workspaces(),
    queryFn: () => packStudioApi.workspaces(),
    refetchInterval: (query) =>
      query.state.data?.some((w) => w.busy) ? WORKSPACE_POLL_MS : false,
  });

export const usePackWorkspace = (id: string) =>
  useQuery({
    queryKey: packStudioKeys.workspace(id),
    queryFn: () => packStudioApi.workspace(id),
    refetchInterval: (query) => pollWhileBusy(query.state.data),
  });

const rememberWorkspace = (client: QueryClient, workspace: PackWorkspace) => {
  client.setQueryData(packStudioKeys.workspace(workspace.id), workspace);
  void client.invalidateQueries({
    queryKey: packStudioKeys.workspaces(),
    exact: true,
  });
};

export const useCreatePackWorkspace = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePackWorkspaceRequest) =>
      packStudioApi.createWorkspace(body),
    onSuccess: (workspace) => {
      rememberWorkspace(client, workspace);
    },
  });
};

export const useRefreshPackWorkspace = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => packStudioApi.refreshWorkspace(id),
    onSuccess: (workspace) => {
      rememberWorkspace(client, workspace);
      void client.invalidateQueries({
        queryKey: packStudioKeys.tree(workspace.id),
      });
    },
  });
};

export const useDeletePackWorkspace = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => packStudioApi.deleteWorkspace(id),
    onSuccess: (_, id) => {
      client.removeQueries({ queryKey: packStudioKeys.workspace(id) });
      void client.invalidateQueries({ queryKey: packStudioKeys.workspaces() });
    },
  });
};

export const usePackTree = (id: string, enabled = true) =>
  useQuery({
    queryKey: packStudioKeys.tree(id),
    queryFn: () => packStudioApi.tree(id),
    enabled,
  });

export const usePackFile = (id: string, path: string | null) =>
  useQuery({
    queryKey: packStudioKeys.file(id, path ?? ""),
    queryFn: () => packStudioApi.readFile(id, path ?? ""),
    enabled: path !== null,
    // Открытый файл не перечитывается сам: внешнюю правку покажет конфликт при записи.
    staleTime: Infinity,
    gcTime: 0,
  });

/**
 * Проверки версии или манифеста, к которому относится файл. `target` это каталог
 * версии или сам манифест (lintTargetOf): одна проверка на всю версию, сколько бы
 * её файлов ни было открыто. `revision` меняется с каждой сохранённой правкой.
 */
export const usePackLint = (
  id: string,
  target: string | null,
  revision: string,
) =>
  useQuery({
    queryKey: packStudioKeys.lint(id, target ?? "", revision),
    queryFn: () => packStudioApi.lint(id, target ?? ""),
    enabled: target !== null,
    placeholderData: (previous) => previous,
    staleTime: Infinity,
  });

/** Подсказки автодополнения версии (`version`: каталог версии файла, versionDirOf). */
export const usePackHints = (id: string, version: string | null) =>
  useQuery({
    queryKey: packStudioKeys.hints(id, version ?? ""),
    queryFn: () => packStudioApi.hints(id, version ?? ""),
    enabled: version !== null,
    staleTime: 60_000,
  });

export const usePackStudioAdmin = () =>
  useQuery({
    queryKey: packStudioKeys.admin(),
    queryFn: () => packStudioApi.admin(),
  });

export const useSetPackStudioAdmin = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => packStudioApi.setAdmin(enabled),
    onSuccess: (admin) => {
      client.setQueryData(packStudioKeys.admin(), admin);
      void client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });
    },
  });
};

export const useAddPackStudioGrant = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePackStudioGrantRequest) =>
      packStudioApi.addGrant(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: packStudioKeys.admin() });
    },
  });
};

export const useRemovePackStudioGrant = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (grantId: string) => packStudioApi.removeGrant(grantId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: packStudioKeys.admin() });
    },
  });
};
