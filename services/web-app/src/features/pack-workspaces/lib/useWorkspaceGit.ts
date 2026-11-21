import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import {
  packStudioApi,
  packStudioKeys,
  type PackGit,
  type PackWorkspace,
} from "@entities/pack-studio";

/**
 * Git каждого готового пространства над репозиторием: по нему список знает,
 * сколько изменений не отправлено. Тот же ключ кэша, что у панели git пространства,
 * поэтому, открыв пространство, человек не ждёт повторного запроса.
 */
export const useWorkspaceGit = (
  workspaces: readonly PackWorkspace[],
): ReadonlyMap<string, PackGit> => {
  const targets = workspaces.filter(
    (w) => w.kind === "git" && w.state === "ready" && !w.busy,
  );
  const data = useQueries({
    queries: targets.map((w) => ({
      queryKey: packStudioKeys.git(w.id),
      queryFn: () => packStudioApi.git(w.id),
    })),
    combine: (results) => results.map((r) => r.data),
  });
  const ids = targets.map((w) => w.id).join("\n");
  return useMemo(() => {
    const map = new Map<string, PackGit>();
    ids.split("\n").forEach((id, i) => {
      const git = data[i];
      if (git) map.set(id, git);
    });
    return map;
  }, [ids, data]);
};
