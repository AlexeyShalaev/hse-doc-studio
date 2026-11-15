import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { catalogKeys } from "@entities/template-catalog";
import type { ArchiveUploadFields } from "../lib/archiveQuery";
import { packCatalogApi } from "./packCatalogApi";
import type { CreateGitSourceRequest, UpdateSourceRequest } from "./schemas";

export const packCatalogKeys = {
  all: ["pack-catalog"] as const,
  overview: () => [...packCatalogKeys.all, "overview"] as const,
  history: (id: string) => [...packCatalogKeys.all, "history", id] as const,
  workspace: (id: string) => [...packCatalogKeys.all, "workspace", id] as const,
};

// Каталог поменялся (применение, выключение, удаление): мастер проекта видит новые паки и версии.
const CATALOG_PACKS_KEY = catalogKeys.all;

const refreshAdmin = (client: QueryClient) => {
  void client.invalidateQueries({ queryKey: packCatalogKeys.all });
  void client.invalidateQueries({ queryKey: CATALOG_PACKS_KEY });
};

/** Каталог установки: источники, остальные паки, пределы. Опрос, пока источник занят. */
export const usePackCatalog = () =>
  useQuery({
    queryKey: packCatalogKeys.overview(),
    queryFn: () => packCatalogApi.overview(),
    refetchInterval: (query) =>
      query.state.data?.sources.some((s) => s.busy) ? 3000 : false,
  });

export const usePackCatalogHistory = (id: string | null) =>
  useQuery({
    queryKey: packCatalogKeys.history(id ?? ""),
    queryFn: () => packCatalogApi.history(id ?? ""),
    enabled: id !== null,
  });

export const useAddGitSource = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateGitSourceRequest) => packCatalogApi.addGit(body),
    onSuccess: () => {
      refreshAdmin(client);
    },
  });
};

export const useAddArchiveSource = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      fields,
    }: {
      file: Blob;
      fields: ArchiveUploadFields;
    }) => packCatalogApi.addArchive(file, fields),
    onSuccess: () => {
      refreshAdmin(client);
    },
  });
};

export const useReplaceArchive = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      file,
      name,
    }: {
      id: string;
      file: Blob;
      name: string;
    }) => packCatalogApi.replaceArchive(id, file, name),
    onSuccess: () => {
      refreshAdmin(client);
    },
  });
};

export const useUpdateSource = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdateSourceRequest }) =>
      packCatalogApi.update(id, body),
    onSuccess: () => {
      refreshAdmin(client);
    },
  });
};

export const useRemoveSource = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => packCatalogApi.remove(id),
    onSuccess: () => {
      refreshAdmin(client);
    },
  });
};

export const useCheckSource = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => packCatalogApi.check(id),
    // Проверка обновляет состояние источника (последняя проверка, ошибка) и в успехе, и в отказе.
    onSettled: () => {
      void client.invalidateQueries({ queryKey: packCatalogKeys.all });
    },
  });
};

export const useApplySource = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, revision }: { id: string; revision: string }) =>
      packCatalogApi.apply(id, revision),
    onSettled: () => {
      refreshAdmin(client);
    },
  });
};

// Локально: папка рабочего пространства в каталоге этой Студии.

export const useWorkspaceCatalog = (workspaceId: string, enabled = true) =>
  useQuery({
    queryKey: packCatalogKeys.workspace(workspaceId),
    queryFn: () => packCatalogApi.workspace(workspaceId),
    enabled,
  });

const refreshWorkspace = (client: QueryClient, workspaceId: string) => {
  void client.invalidateQueries({
    queryKey: packCatalogKeys.workspace(workspaceId),
  });
  void client.invalidateQueries({ queryKey: CATALOG_PACKS_KEY });
};

export const useCheckWorkspaceCatalog = (workspaceId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (replaceBuiltin: boolean) =>
      packCatalogApi.checkWorkspace(workspaceId, replaceBuiltin),
    onSettled: () => {
      void client.invalidateQueries({
        queryKey: packCatalogKeys.workspace(workspaceId),
      });
    },
  });
};

export const useApplyWorkspaceCatalog = (workspaceId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (revision: string) =>
      packCatalogApi.applyWorkspace(workspaceId, revision),
    onSettled: () => {
      refreshWorkspace(client, workspaceId);
    },
  });
};

export const useSetWorkspaceCatalogEnabled = (workspaceId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      packCatalogApi.setWorkspaceEnabled(workspaceId, enabled),
    onSuccess: (data) => {
      client.setQueryData(packCatalogKeys.workspace(workspaceId), data);
      refreshWorkspace(client, workspaceId);
    },
  });
};

export const useDisconnectWorkspaceCatalog = (workspaceId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => packCatalogApi.disconnectWorkspace(workspaceId),
    onSuccess: () => {
      client.setQueryData(packCatalogKeys.workspace(workspaceId), {
        source: null,
      });
      refreshWorkspace(client, workspaceId);
    },
  });
};
