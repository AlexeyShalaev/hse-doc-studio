import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { documentKeys } from "@entities/document";
import { projectKeys } from "@entities/project";
import { vcsKeys } from "@entities/vcs";
import {
  type ApplyTemplateUpdateParams,
  type RevertTemplateUpdateParams,
  type TemplateDiffParams,
  templateUpdateApi,
} from "./templateUpdateApi";

export const templateUpdateKeys = {
  all: ["template-update"] as const,
  status: (projectId: string) =>
    [...templateUpdateKeys.all, "status", projectId] as const,
  plan: (projectId: string, toVersion: string) =>
    [...templateUpdateKeys.all, "plan", projectId, toVersion] as const,
  diff: (projectId: string, params: TemplateDiffParams) =>
    [
      ...templateUpdateKeys.all,
      "diff",
      projectId,
      params.path,
      params.view,
      params.toVersion ?? "",
      params.resolution ?? "",
    ] as const,
  compare: (projectId: string) =>
    [...templateUpdateKeys.all, "compare", projectId] as const,
};

export const useTemplateUpdateStatus = (projectId: string) =>
  useQuery({
    queryKey: templateUpdateKeys.status(projectId),
    queryFn: () => templateUpdateApi.getStatus(projectId),
    enabled: !!projectId,
  });

// План — снимок диска на момент запроса: не кэшируем надолго, иначе отпечаток
// устареет раньше, чем пользователь нажмёт «Применить».
export const useTemplateUpdatePlan = (
  projectId: string,
  toVersion: string | null,
) =>
  useQuery({
    queryKey: templateUpdateKeys.plan(projectId, toVersion ?? ""),
    queryFn: () => templateUpdateApi.plan(projectId, toVersion ?? ""),
    enabled: !!projectId && !!toVersion,
    staleTime: 0,
    gcTime: 0,
    retry: false,
  });

export const useTemplateFileDiff = (
  projectId: string,
  params: TemplateDiffParams | null,
) =>
  useQuery({
    queryKey: params
      ? templateUpdateKeys.diff(projectId, params)
      : [...templateUpdateKeys.all, "diff", projectId, "none"],
    queryFn: () =>
      params
        ? templateUpdateApi.getDiff(projectId, params)
        : Promise.reject(new Error("no file selected")),
    enabled: !!projectId && params !== null,
    staleTime: 0,
  });

export const useCompareWithTemplate = (projectId: string, enabled: boolean) =>
  useQuery({
    queryKey: templateUpdateKeys.compare(projectId),
    queryFn: () => templateUpdateApi.compare(projectId),
    enabled: !!projectId && enabled,
  });

// Обновление меняет файлы, lock и историю: освежаем всё, что от них зависит.
const invalidateAfterUpdate = (
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
): void => {
  void queryClient.invalidateQueries({ queryKey: templateUpdateKeys.all });
  void queryClient.invalidateQueries({
    queryKey: projectKeys.detail(projectId),
  });
  void queryClient.invalidateQueries({ queryKey: vcsKeys.all });
  void queryClient.invalidateQueries({ queryKey: documentKeys.all });
  void queryClient.invalidateQueries({ queryKey: ["files"] });
};

export const useApplyTemplateUpdate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: ApplyTemplateUpdateParams;
    }) => templateUpdateApi.apply(projectId, params),
    onSuccess: (_, { projectId }) => {
      invalidateAfterUpdate(queryClient, projectId);
    },
  });
};

export const useRevertTemplateUpdate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: RevertTemplateUpdateParams;
    }) => templateUpdateApi.revert(projectId, params),
    onSuccess: (result, { projectId }) => {
      if (result.applied) invalidateAfterUpdate(queryClient, projectId);
    },
  });
};

export const useSetTemplateTracking = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      path,
      tracked,
    }: {
      projectId: string;
      path: string;
      tracked: boolean;
    }) => templateUpdateApi.setTracking(projectId, path, tracked),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: templateUpdateKeys.compare(projectId),
      });
    },
  });
};
