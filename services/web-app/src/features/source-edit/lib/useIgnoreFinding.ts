import { useMutation, useQueryClient } from "@tanstack/react-query";
import { documentKeys, fileKeys } from "@entities/document";
import { apiClient } from "@shared/api/client";
import { i18n, toast, toPosixPath } from "@shared/lib";
import { insertSuppression } from "./insertSuppression";

type IgnoreFindingArgs = {
  /** Project-relative path of the file the finding is in. */
  file: string;
  /** 1-based line of the finding. */
  line: number;
  ruleId: string;
};

/**
 * Suppresses one finding from outside the editor (e.g. the «Проверки» tab) by
 * inserting a `% hse-noqa: <rule>` comment into its source line: read the file,
 * append the marker, write it back, then refresh findings. Used when the file
 * isn't open in the editor.
 */
export const useIgnoreFinding = (projectId: string, docId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, line, ruleId }: IgnoreFindingArgs) => {
      const path = toPosixPath(file);
      const res = await apiClient.get(`/projects/${projectId}/files/${path}`, {
        responseType: "text",
      });
      const content = res.data as string;
      const next = insertSuppression(content, line, ruleId);
      if (next === content) return path;
      await apiClient.put(`/projects/${projectId}/files/${path}`, next, {
        headers: { "Content-Type": "text/plain" },
      });
      return path;
    },
    onSuccess: (path) => {
      void queryClient.invalidateQueries({
        queryKey: fileKeys.content(projectId, path),
      });
      void queryClient.invalidateQueries({
        queryKey: documentKeys.checkResults(projectId, docId),
      });
      toast.info(i18n.t("sourceEdit:ignore.success"));
    },
    onError: () => {
      toast.error(i18n.t("sourceEdit:ignore.error"));
    },
  });
};
