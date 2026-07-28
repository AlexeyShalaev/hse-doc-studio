import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { UpdateDocumentRequest } from "@shared/api/types";
import { documentApi } from "./documentApi";

type DocumentItem = Awaited<ReturnType<typeof documentApi.list>>[number];
type CompileItem = Awaited<ReturnType<typeof documentApi.listCompiles>>[number];
type CompileDetail = Awaited<ReturnType<typeof documentApi.getCompile>>;
type TriggerResult = Awaited<ReturnType<typeof documentApi.triggerCompile>>;
type CancelResult = Awaited<ReturnType<typeof documentApi.cancelCompile>>;
type CheckResults = Awaited<ReturnType<typeof documentApi.getCheckResults>>;
type CheckRules = Awaited<ReturnType<typeof documentApi.getCheckRules>>;

export const documentKeys = {
  all: ["documents"] as const,
  lists: (projectId: string) =>
    [...documentKeys.all, "list", projectId] as const,
  detail: (projectId: string, docId: string) =>
    [...documentKeys.all, "detail", projectId, docId] as const,
  compiles: (projectId: string, docId: string) =>
    [...documentKeys.all, "compiles", projectId, docId] as const,
  compile: (projectId: string, docId: string, compileId: string) =>
    [...documentKeys.all, "compile", projectId, docId, compileId] as const,
  checkResults: (projectId: string, docId: string) =>
    [...documentKeys.all, "checkResults", projectId, docId] as const,
  checkRules: (projectId: string, docId: string) =>
    [...documentKeys.all, "checkRules", projectId, docId] as const,
};

export const useDocuments = (projectId: string) =>
  useQuery({
    queryKey: documentKeys.lists(projectId),
    queryFn: () => documentApi.list(projectId),
    enabled: !!projectId,
  });

export const useDocument = (projectId: string, docId: string) =>
  useQuery({
    queryKey: documentKeys.detail(projectId, docId),
    queryFn: () => documentApi.get(projectId, docId),
    enabled: !!projectId && !!docId,
  });

export const useUpdateDocument = () => {
  const queryClient = useQueryClient();
  return useMutation<
    DocumentItem,
    Error,
    { projectId: string; docId: string; data: UpdateDocumentRequest }
  >({
    mutationFn: ({ projectId, docId, data }) =>
      documentApi.update(projectId, docId, data),
    onSuccess: (doc, { projectId, docId }) => {
      queryClient.setQueryData(documentKeys.detail(projectId, docId), doc);
      // Switching chosen_variant makes the backend materialise the variant's
      // files and reset the status — refetch the detail (not just overlay the
      // PATCH response) and the list so tabs/preview/nav pick up the new
      // source/output paths and engine.
      void queryClient.invalidateQueries({
        queryKey: documentKeys.detail(projectId, docId),
      });
      void queryClient.invalidateQueries({
        queryKey: documentKeys.lists(projectId),
      });
      // checks_override is part of the document — when it changes, the rules
      // list needs a refetch so `enabled` flags reflect the new override, and
      // the results need a refetch so finding severities (re-resolved on read)
      // reflect the new override without waiting for a recompile.
      void queryClient.invalidateQueries({
        queryKey: documentKeys.checkRules(projectId, docId),
      });
      void queryClient.invalidateQueries({
        queryKey: documentKeys.checkResults(projectId, docId),
      });
    },
  });
};

const invalidateAfterCustomFileChange = (
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
  docId: string,
  doc: DocumentItem,
): void => {
  queryClient.setQueryData(documentKeys.detail(projectId, docId), doc);
  void queryClient.invalidateQueries({
    queryKey: documentKeys.detail(projectId, docId),
  });
  void queryClient.invalidateQueries({
    queryKey: documentKeys.lists(projectId),
  });
  void queryClient.invalidateQueries({
    queryKey: documentKeys.checkRules(projectId, docId),
  });
  void queryClient.invalidateQueries({
    queryKey: documentKeys.checkResults(projectId, docId),
  });
};

export const useUploadCustomFile = () => {
  const queryClient = useQueryClient();
  return useMutation<
    DocumentItem,
    Error,
    { projectId: string; docId: string; file: File }
  >({
    mutationFn: ({ projectId, docId, file }) =>
      documentApi.uploadCustomFile(projectId, docId, file),
    onSuccess: (doc, { projectId, docId }) => {
      invalidateAfterCustomFileChange(queryClient, projectId, docId, doc);
    },
  });
};

export const useRemoveCustomFile = () => {
  const queryClient = useQueryClient();
  return useMutation<
    DocumentItem,
    Error,
    { projectId: string; docId: string; deleteFile?: boolean }
  >({
    mutationFn: ({ projectId, docId, deleteFile }) =>
      documentApi.removeCustomFile(projectId, docId, deleteFile),
    onSuccess: (doc, { projectId, docId }) => {
      invalidateAfterCustomFileChange(queryClient, projectId, docId, doc);
    },
  });
};

export const useTriggerCompile = () => {
  const queryClient = useQueryClient();
  return useMutation<
    TriggerResult,
    Error,
    { projectId: string; docId: string }
  >({
    mutationFn: ({ projectId, docId }) =>
      documentApi.triggerCompile(projectId, docId),
    onSuccess: (_, { projectId, docId }) => {
      void queryClient.invalidateQueries({
        queryKey: documentKeys.compiles(projectId, docId),
      });
      void queryClient.invalidateQueries({
        queryKey: documentKeys.lists(projectId),
      });
    },
  });
};

export const useCancelCompile = () => {
  const queryClient = useQueryClient();
  return useMutation<
    CancelResult,
    Error,
    { projectId: string; compileId: string }
  >({
    mutationFn: ({ projectId, compileId }) =>
      documentApi.cancelCompile(projectId, compileId),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: documentKeys.lists(projectId),
      });
    },
  });
};

export const useCompiles = (projectId: string, docId: string) =>
  useQuery<CompileItem[]>({
    queryKey: documentKeys.compiles(projectId, docId),
    queryFn: () => documentApi.listCompiles(projectId, docId),
    enabled: !!projectId && !!docId,
  });

export const useCompile = (
  projectId: string,
  docId: string,
  compileId: string,
) =>
  useQuery<CompileDetail>({
    queryKey: documentKeys.compile(projectId, docId, compileId),
    queryFn: () => documentApi.getCompile(projectId, docId, compileId),
    enabled: !!projectId && !!docId && !!compileId,
  });

/**
 * Check results for a document. With `scope: "document"` the backend keeps only
 * findings located in this document's own file or a file it imports — used by
 * the «Проверки» tab. The default ("all") preserves the original key/URL so the
 * editor's cross-file diagnostics (useProjectDiagnostics) are unaffected, and
 * the two scopes are cached separately. Invalidating the (scope-less) prefix
 * `checkResults(projectId, docId)` still refreshes both via prefix matching.
 */
export const useCheckResults = (
  projectId: string,
  docId: string,
  scope: "all" | "document" = "all",
) =>
  useQuery<CheckResults>({
    queryKey:
      scope === "document"
        ? [...documentKeys.checkResults(projectId, docId), "document"]
        : documentKeys.checkResults(projectId, docId),
    queryFn: () =>
      documentApi.getCheckResults(
        projectId,
        docId,
        scope === "document" ? "document" : undefined,
      ),
    enabled: !!projectId && !!docId,
  });

export const useCheckRules = (projectId: string, docId: string) =>
  useQuery<CheckRules>({
    queryKey: documentKeys.checkRules(projectId, docId),
    queryFn: () => documentApi.getCheckRules(projectId, docId),
    enabled: !!projectId && !!docId,
  });
