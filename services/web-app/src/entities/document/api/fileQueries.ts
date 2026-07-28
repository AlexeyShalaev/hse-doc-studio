import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback } from "react";
import axios from "axios";
import { z } from "zod";
import { apiClient } from "@shared/api/client";
import type { FileTreeItemResponse } from "@shared/api/types";

const FileTreeItemSchema = z.object({
  path: z.string(),
  size: z.number(),
  modified_at: z.string(),
  // Older backends omit this; default to deletable so the UI never wrongly locks.
  deletable: z.boolean().optional().default(true),
  is_dir: z.boolean().optional().default(false),
});

const FileTreeResponseSchema = z.array(FileTreeItemSchema);

export const fileKeys = {
  tree: (projectId: string) => ["files", projectId, "tree"] as const,
  content: (projectId: string, path: string) =>
    ["files", projectId, path] as const,
  version: (projectId: string, path: string) =>
    ["files", projectId, path, "version"] as const,
};

/**
 * Тот же файл пользователь правит и в Студии, и снаружи (VS Code) — папка
 * проекта обычная. Поэтому содержимое возят вместе с ETag: он едет обратно в
 * `If-Match`, и бэкенд отказывается затирать правку, сделанную снаружи.
 */
export type FileWithVersion = { content: string; etag: string | null };

export const fetchFileWithVersion = (
  projectId: string,
  path: string,
): Promise<FileWithVersion> =>
  apiClient
    .get(`/projects/${projectId}/files/${path}`, { responseType: "text" })
    .then((r) => ({
      content: r.data as string,
      etag: (r.headers.etag as string | undefined) ?? null,
    }));

const FileVersionSchema = z.object({ etag: z.string(), size: z.number() });

/** Опрос версии открытого файла: изменился ли он на диске под нами. */
export const useFileVersion = (
  projectId: string,
  path: string,
  {
    enabled = true,
    intervalMs = 4000,
  }: { enabled?: boolean; intervalMs?: number } = {},
) =>
  useQuery({
    queryKey: fileKeys.version(projectId, path),
    queryFn: () =>
      apiClient
        .get(`/projects/${projectId}/file-version/${path}`)
        .then((r) => FileVersionSchema.parse(r.data)),
    enabled: enabled && !!projectId && !!path,
    // Слежение за файловой системой изнутри контейнера не работает: события
    // inotify не переходят границу бинд-маунта. Поэтому опрос — и только для
    // открытых вкладок, ответ в десяток байт.
    refetchInterval: intervalMs,
    refetchIntervalInBackground: false,
    staleTime: 0,
    // Пропавший файл — не повод ретраить: вкладка покажет это отдельно.
    retry: false,
  });

export const useFileTree = (projectId: string) =>
  useQuery<FileTreeItemResponse[]>({
    queryKey: fileKeys.tree(projectId),
    queryFn: () =>
      apiClient
        .get(`/projects/${projectId}/files`)
        .then((r) => FileTreeResponseSchema.parse(r.data)),
    // Файл, созданный в VS Code, должен появиться в дереве сам, без перезагрузки.
    refetchInterval: 15000,
    refetchIntervalInBackground: false,
    enabled: !!projectId,
  });

/** Содержимое вместе с версией — для редактора, который будет его сохранять. */
export const useFileWithVersion = (projectId: string, path: string) =>
  useQuery({
    queryKey: fileKeys.content(projectId, path),
    queryFn: () => fetchFileWithVersion(projectId, path),
    enabled: !!projectId && !!path,
  });

/** Только текст — тому, кто файл лишь читает. Кеш общий с `useFileWithVersion`. */
export const useFile = (projectId: string, path: string) =>
  useQuery({
    queryKey: fileKeys.content(projectId, path),
    queryFn: () => fetchFileWithVersion(projectId, path),
    enabled: !!projectId && !!path,
    select: (data: FileWithVersion) => data.content,
  });

/**
 * Load an arbitrary set of project text files without changing hook order.
 * The visual editor uses this for direct LaTeX inputs, whose number depends
 * on the open document. Missing files simply stay absent from the returned
 * map, allowing the editor to keep an honest loading/fallback block.
 */
export const useFiles = (projectId: string, paths: readonly string[]) => {
  const combine = useCallback(
    (results: readonly { readonly data: string | undefined }[]) => {
      const files: Record<string, string> = {};
      results.forEach((result, index) => {
        const path = paths[index];
        if (path !== undefined && result.data !== undefined) {
          files[path] = result.data;
        }
      });
      return files;
    },
    [paths],
  );

  return useQueries({
    queries: paths.map((path) => ({
      queryKey: fileKeys.content(projectId, path),
      queryFn: () =>
        apiClient
          .get(`/projects/${projectId}/files/${path}`, {
            responseType: "text",
          })
          .then((response) => response.data as string),
      enabled: !!projectId && !!path,
    })),
    combine,
  });
};

/** Файл изменился на диске с момента загрузки — сохранять поверх нельзя. */
export class StaleFileError extends Error {
  constructor(
    readonly diskContent: string,
    readonly diskEtag: string,
  ) {
    super("file changed on disk");
    this.name = "StaleFileError";
  }
}

const StaleDetailSchema = z.object({
  code: z.literal("stale_file"),
  etag: z.string(),
  content: z.string(),
});

/**
 * Сохранение файла. `ifMatch` — версия, на которую опирался редактор: без неё
 * запись безусловная (так пишут агент и загрузка бинарников), с ней бэкенд
 * откажет 409-м, если файл успели поправить снаружи.
 */
export const usePutFile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      path,
      content,
      ifMatch,
    }: {
      projectId: string;
      path: string;
      content: string;
      ifMatch?: string | null;
    }): Promise<{ etag: string | null }> => {
      try {
        const response = await apiClient.put(
          `/projects/${projectId}/files/${path}`,
          content,
          {
            headers: {
              "Content-Type": "text/plain",
              ...(ifMatch ? { "If-Match": ifMatch } : {}),
            },
          },
        );
        return { etag: (response.headers.etag as string | undefined) ?? null };
      } catch (error) {
        const detail = axios.isAxiosError(error)
          ? StaleDetailSchema.safeParse(
              (error.response?.data as { detail?: unknown } | undefined)
                ?.detail,
            )
          : null;
        if (detail?.success) {
          throw new StaleFileError(detail.data.content, detail.data.etag);
        }
        throw error;
      }
    },
    onSuccess: (_, { projectId, path }) => {
      void queryClient.invalidateQueries({
        queryKey: fileKeys.content(projectId, path),
      });
      void queryClient.invalidateQueries({
        queryKey: fileKeys.version(projectId, path),
      });
    },
  });
};

export const useDeleteFile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, path }: { projectId: string; path: string }) =>
      apiClient.delete(`/projects/${projectId}/files/${path}`),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: fileKeys.tree(projectId),
      });
    },
  });
};

export const useMoveFile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      src,
      dst,
    }: {
      projectId: string;
      src: string;
      dst: string;
    }) => apiClient.post(`/projects/${projectId}/file-ops/move`, { src, dst }),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: fileKeys.tree(projectId),
      });
    },
  });
};

export const useCreateDir = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, path }: { projectId: string; path: string }) =>
      apiClient.post(`/projects/${projectId}/file-ops/mkdir`, { path }),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: fileKeys.tree(projectId),
      });
    },
  });
};

export const useUploadFile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      path,
      data,
      contentType,
    }: {
      projectId: string;
      path: string;
      data: ArrayBuffer | Blob;
      contentType?: string;
    }) =>
      apiClient.put(`/projects/${projectId}/files/${path}`, data, {
        headers: {
          "Content-Type": contentType ?? "application/octet-stream",
        },
      }),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: fileKeys.tree(projectId),
      });
    },
  });
};
