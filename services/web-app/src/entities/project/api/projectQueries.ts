import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  CreateProjectRequest,
  ConnectProjectRequest,
  UpdateProjectRequest,
} from "@shared/api/types";
import { projectApi } from "./projectApi";

type ProjectItem = Awaited<ReturnType<typeof projectApi.get>>;
type ProjectCheckRules = Awaited<ReturnType<typeof projectApi.getCheckRules>>;
type NdaStatus = Awaited<ReturnType<typeof projectApi.getNda>>;

export const projectKeys = {
  all: ["projects"] as const,
  lists: () => [...projectKeys.all, "list"] as const,
  detail: (id: string) => [...projectKeys.all, "detail", id] as const,
  checkRules: (id: string) => [...projectKeys.all, "checkRules", id] as const,
  nda: (id: string) => [...projectKeys.all, "nda", id] as const,
  suggestions: () => [...projectKeys.all, "suggestions"] as const,
};

export const useProjects = () =>
  useQuery({
    queryKey: projectKeys.lists(),
    queryFn: () => projectApi.list(),
  });

// Create-wizard hints (folder roots + authors) aggregated from existing
// projects. Cached a few minutes.
export const useProjectSuggestions = () =>
  useQuery({
    queryKey: projectKeys.suggestions(),
    queryFn: () => projectApi.suggestions(),
    staleTime: 5 * 60 * 1000,
  });

export const useProject = (id: string) =>
  useQuery({
    queryKey: projectKeys.detail(id),
    queryFn: () => projectApi.get(id),
    enabled: !!id,
  });

export const useCreateProject = () => {
  const queryClient = useQueryClient();
  return useMutation<ProjectItem, Error, CreateProjectRequest>({
    mutationFn: (data) => projectApi.create(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
    },
  });
};

export const useConnectProject = () => {
  const queryClient = useQueryClient();
  return useMutation<ProjectItem, Error, ConnectProjectRequest>({
    mutationFn: (data) => projectApi.connect(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
    },
  });
};

export const useUpdateProject = () => {
  const queryClient = useQueryClient();
  return useMutation<
    ProjectItem,
    Error,
    { id: string; data: UpdateProjectRequest }
  >({
    mutationFn: ({ id, data }) => projectApi.update(id, data),
    onSuccess: (project) => {
      queryClient.setQueryData(projectKeys.detail(project.id), project);
      void queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
      // Project-level checks_override changes affect rule enabled flags and
      // effective severities — refetch the project rules list.
      void queryClient.invalidateQueries({
        queryKey: projectKeys.checkRules(project.id),
      });
      // Мета-поле «Руководства в комплекте» (manuals) меняет состав документов
      // (is_doc_active) — навигация/файлы/подписи должны перечитаться, иначе
      // виден старый набор доков. Ключи всех doc-запросов начинаются с
      // ["documents", ...] (см. documentKeys.all); импортировать их сюда нельзя
      // по FSD — сущности не зависят друг от друга, поэтому литерал.
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["signatures"] });
    },
  });
};

export const useUpdateTeamSet = () => {
  const queryClient = useQueryClient();
  return useMutation<
    ProjectItem,
    Error,
    { id: string; authorSlug: string | null; enabled: boolean }
  >({
    mutationFn: ({ id, authorSlug, enabled }) =>
      projectApi.updateTeamSet(id, { author_slug: authorSlug, enabled }),
    onSuccess: (project) => {
      queryClient.setQueryData(projectKeys.detail(project.id), project);
      // Состав документов проекта изменился — навигация/файлы/подписи должны
      // перечитаться (все doc-ключи начинаются с ["documents", ...]).
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["signatures"] });
      void queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
    },
  });
};

export const useMoveProject = () => {
  const queryClient = useQueryClient();
  return useMutation<ProjectItem, Error, { id: string; folder: string }>({
    mutationFn: ({ id, folder }) => projectApi.move(id, folder),
    onSuccess: (project) => {
      // The project keeps its id (the route stays valid); only its folder
      // changed. Refresh the detail + list caches with the new location.
      queryClient.setQueryData(projectKeys.detail(project.id), project);
      void queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
    },
  });
};

export const useProjectCheckRules = (id: string) =>
  useQuery<ProjectCheckRules>({
    queryKey: projectKeys.checkRules(id),
    queryFn: () => projectApi.getCheckRules(id),
    enabled: !!id,
  });

export const useRemoveProject = () => {
  const queryClient = useQueryClient();
  return useMutation<undefined, Error, string>({
    mutationFn: async (id) => {
      await projectApi.remove(id);
      return undefined;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
    },
  });
};

// NDA file group: whether the template offers NDA files and whether the
// project currently has any (drives the settings toggle's toasts + prompt).
export const useNdaStatus = (id: string) =>
  useQuery<NdaStatus>({
    queryKey: projectKeys.nda(id),
    queryFn: () => projectApi.getNda(id),
    enabled: !!id,
    // Глобальный staleTime (30с) держал NDA-статус «свежим», поэтому при
    // открытии вкладки NDA после смены свитча в настройках список файлов
    // не перечитывался (виден старый набор до перезагрузки страницы).
    // Всегда перечитываем при монтировании вкладки — актуальный состав с бэка.
    staleTime: 0,
    refetchOnMount: "always",
  });

export const useInstantiateNda = () => {
  const queryClient = useQueryClient();
  return useMutation<NdaStatus, Error, string>({
    mutationFn: (id) => projectApi.instantiateNda(id),
    onSuccess: (status, id) => {
      queryClient.setQueryData(projectKeys.nda(id), status);
    },
  });
};

export const useDeleteNdaFiles = () => {
  const queryClient = useQueryClient();
  return useMutation<NdaStatus, Error, string>({
    mutationFn: (id) => projectApi.deleteNdaFiles(id),
    onSuccess: (status, id) => {
      queryClient.setQueryData(projectKeys.nda(id), status);
    },
  });
};
