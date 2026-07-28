import { useQueryClient } from "@tanstack/react-query";
import { aiProviderKeys } from "@entities/ai-provider";
import { aiRuntimeKeys } from "@entities/ai-runtime";

/**
 * Refresh everything the runtime can change. Lives in the feature layer because
 * it crosses two entities: runtime queries AND the `ollama` provider list that
 * the backend syncs on start/pull/delete (entities may not import each other).
 */
export const useInvalidateLocalRuntime = () => {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: aiRuntimeKeys.status() });
    void queryClient.invalidateQueries({ queryKey: aiRuntimeKeys.catalog() });
    void queryClient.invalidateQueries({ queryKey: aiProviderKeys.lists() });
  };
};
