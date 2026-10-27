import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  type CreateBranchParams,
  type CreateTagParams,
  type DiffParams,
  type RestoreParams,
  type UpdateVcsSettingsParams,
  type VcsHistoryParams,
  vcsApi,
} from "./vcsApi";

export const vcsKeys = {
  all: ["vcs"] as const,
  status: (projectId: string) => [...vcsKeys.all, "status", projectId] as const,
  history: (projectId: string, docId?: string) =>
    [...vcsKeys.all, "history", projectId, docId ?? "*"] as const,
  historyPage: (projectId: string, params: VcsHistoryParams) =>
    [...vcsKeys.all, "history", projectId, "page", params] as const,
  historyFacets: (projectId: string) =>
    [...vcsKeys.all, "history", projectId, "facets"] as const,
  commit: (projectId: string, commitId: string) =>
    [...vcsKeys.all, "commit", projectId, commitId] as const,
  diff: (projectId: string, params: DiffParams) =>
    [
      ...vcsKeys.all,
      "diff",
      projectId,
      params.fromId ?? "",
      params.toId ?? "",
      params.path ?? "",
    ] as const,
  settings: (projectId: string) =>
    [...vcsKeys.all, "settings", projectId] as const,
  branches: (projectId: string) =>
    [...vcsKeys.all, "branches", projectId] as const,
  tags: (projectId: string) => [...vcsKeys.all, "tags", projectId] as const,
};

export const useVcsStatus = (projectId: string) =>
  useQuery({
    queryKey: vcsKeys.status(projectId),
    queryFn: () => vcsApi.getStatus(projectId),
    enabled: !!projectId,
  });

export const useVcsHistory = (projectId: string, docId?: string) =>
  useQuery({
    queryKey: vcsKeys.history(projectId, docId),
    queryFn: () => vcsApi.getHistory(projectId, docId),
    enabled: !!projectId,
  });

// Страница истории с фильтрами: ключ зависит от всего набора условий.
export const useVcsHistoryPage = (
  projectId: string,
  params: VcsHistoryParams,
) =>
  useQuery({
    queryKey: vcsKeys.historyPage(projectId, params),
    queryFn: () => vcsApi.getHistoryPage(projectId, params),
    enabled: !!projectId,
    placeholderData: (previous) => previous,
  });

export const VCS_HISTORY_PAGE_SIZE = 100;

// Бесконечный список «Показать ещё»: страницы идут по limit/offset.
export const useInfiniteVcsHistory = (
  projectId: string,
  params: Omit<VcsHistoryParams, "limit" | "offset">,
  pageSize = VCS_HISTORY_PAGE_SIZE,
) =>
  useInfiniteQuery({
    queryKey: [
      ...vcsKeys.historyPage(projectId, { ...params, limit: pageSize }),
      "infinite",
    ],
    queryFn: ({ pageParam }) =>
      vcsApi.getHistoryPage(projectId, {
        ...params,
        limit: pageSize,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < pageSize
        ? undefined
        : allPages.reduce((total, page) => total + page.length, 0),
    enabled: !!projectId,
    placeholderData: (previous) => previous,
  });

export const useVcsHistoryFacets = (projectId: string) =>
  useQuery({
    queryKey: vcsKeys.historyFacets(projectId),
    queryFn: () => vcsApi.getHistoryFacets(projectId),
    enabled: !!projectId,
  });

export const useVcsCommit = (projectId: string, commitId: string | null) =>
  useQuery({
    queryKey: vcsKeys.commit(projectId, commitId ?? ""),
    queryFn: () => vcsApi.getCommit(projectId, commitId ?? ""),
    enabled: !!projectId && !!commitId,
  });

export const useVcsDiff = (projectId: string, params: DiffParams) =>
  useQuery({
    queryKey: vcsKeys.diff(projectId, params),
    queryFn: () => vcsApi.getDiff(projectId, params),
    enabled: !!projectId && (!!params.toId || !!params.fromId),
  });

export const useVcsSettings = (projectId: string) =>
  useQuery({
    queryKey: vcsKeys.settings(projectId),
    queryFn: () => vcsApi.getSettings(projectId),
    enabled: !!projectId,
  });

// Invalidate the whole VCS namespace for a project after any write — cheap and
// keeps the timeline, status badge and diffs consistent.
const invalidateProjectVcs = (
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
): void => {
  void queryClient.invalidateQueries({ queryKey: vcsKeys.status(projectId) });
  void queryClient.invalidateQueries({
    queryKey: [...vcsKeys.all, "history", projectId],
  });
  void queryClient.invalidateQueries({ queryKey: vcsKeys.settings(projectId) });
  void queryClient.invalidateQueries({ queryKey: vcsKeys.branches(projectId) });
  void queryClient.invalidateQueries({ queryKey: vcsKeys.tags(projectId) });
};

export const useInitVcs = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => vcsApi.init(projectId),
    onSuccess: (_, projectId) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};

export const useCreateVcsSnapshot = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      message,
      docId,
    }: {
      projectId: string;
      message: string;
      docId?: string;
    }) => vcsApi.createSnapshot(projectId, message, docId),
    onSuccess: (_, { projectId }) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};

export const useRestoreVcs = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: RestoreParams;
    }) => vcsApi.restore(projectId, params),
    onSuccess: (_, { projectId }) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};

export const useUpdateVcsSettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: UpdateVcsSettingsParams;
    }) => vcsApi.updateSettings(projectId, params),
    onSuccess: (_, { projectId }) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};

export const useVcsBranches = (projectId: string) =>
  useQuery({
    queryKey: vcsKeys.branches(projectId),
    queryFn: () => vcsApi.listBranches(projectId),
    enabled: !!projectId,
  });

export const useVcsTags = (projectId: string) =>
  useQuery({
    queryKey: vcsKeys.tags(projectId),
    queryFn: () => vcsApi.listTags(projectId),
    enabled: !!projectId,
  });

export const useCreateVcsBranch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: CreateBranchParams;
    }) => vcsApi.createBranch(projectId, params),
    onSuccess: (_, { projectId }) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};

export const useSwitchVcsBranch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, name }: { projectId: string; name: string }) =>
      vcsApi.switchBranch(projectId, name),
    onSuccess: (_, { projectId }) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};

export const useDeleteVcsBranch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, name }: { projectId: string; name: string }) =>
      vcsApi.deleteBranch(projectId, name),
    onSuccess: (_, { projectId }) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};

export const useCreateVcsTag = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: CreateTagParams;
    }) => vcsApi.createTag(projectId, params),
    onSuccess: (_, { projectId }) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};

export const useDeleteVcsTag = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, name }: { projectId: string; name: string }) =>
      vcsApi.deleteTag(projectId, name),
    onSuccess: (_, { projectId }) => {
      invalidateProjectVcs(queryClient, projectId);
    },
  });
};
