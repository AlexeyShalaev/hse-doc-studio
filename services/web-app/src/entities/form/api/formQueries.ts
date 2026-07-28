import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formApi } from "./formApi";
import type { FormData, UpdateFormRequest } from "./formApi";

export const formKeys = {
  all: ["forms"] as const,
  list: (projectId: string) => [...formKeys.all, projectId, "list"] as const,
  detail: (projectId: string, formId: string) =>
    [...formKeys.all, projectId, formId] as const,
  preview: (projectId: string, formId: string) =>
    [...formKeys.all, projectId, formId, "preview"] as const,
};

export const useForms = (projectId: string) =>
  useQuery({
    queryKey: formKeys.list(projectId),
    queryFn: () => formApi.list(projectId),
    enabled: !!projectId,
  });

export const useForm = (projectId: string, formId: string) =>
  useQuery({
    queryKey: formKeys.detail(projectId, formId),
    queryFn: () => formApi.get(projectId, formId),
    enabled: !!projectId && !!formId,
  });

export const useFormPreview = (
  projectId: string,
  formId: string,
  enabled: boolean,
) =>
  useQuery({
    queryKey: formKeys.preview(projectId, formId),
    queryFn: () => formApi.preview(projectId, formId),
    enabled: enabled && !!projectId && !!formId,
  });

export const useUpdateForm = () => {
  const queryClient = useQueryClient();
  return useMutation<
    FormData,
    Error,
    { projectId: string; formId: string; body: UpdateFormRequest }
  >({
    mutationFn: ({ projectId, formId, body }) =>
      formApi.update(projectId, formId, body),
    onSuccess: (data, { projectId, formId }) => {
      queryClient.setQueryData(formKeys.detail(projectId, formId), data);
      // The rendered preview + the list's complete/completed flags now stale.
      void queryClient.invalidateQueries({
        queryKey: formKeys.preview(projectId, formId),
      });
      void queryClient.invalidateQueries({
        queryKey: formKeys.list(projectId),
      });
    },
  });
};
