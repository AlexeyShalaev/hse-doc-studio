import { useMutation, useQueryClient } from "@tanstack/react-query";
import { exportImportApi } from "../api/exportImportApi";
import type { ImportRequest, ImportResult } from "../api/exportImportApi";

export const useImportData = () => {
  const queryClient = useQueryClient();
  return useMutation<ImportResult, Error, ImportRequest>({
    mutationFn: (request) => exportImportApi.importData(request),
    onSuccess: () => {
      // Imported settings/providers landed on disk — refetch both so the live
      // UI (theme, default provider, providers list) reflects them immediately.
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
      void queryClient.invalidateQueries({ queryKey: ["ai-providers"] });
    },
  });
};
