import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  packStudioKeys,
  usePackChecks,
  usePackFilesRevision,
  usePackGit,
  type PackCiStatus,
} from "@entities/pack-studio";
import { useSpace } from "./SpaceContext";

const NONE: readonly string[] = [];

/**
 * Каталоги версий принятого запроса, о выпуске которых пространство ещё не знает: в дереве они
 * не выпущены, но это не черновики («принята, обновите пространство»). Считает сервер (поле
 * `accepted_versions` статуса проверок): запрос слит и версия после этого не правилась. Запросы и
 * кэш те же, что у «Изменений».
 */
export const useAcceptedVersions = (): readonly string[] => {
  const { workspace } = useSpace();
  const client = useQueryClient();
  const id = workspace.id;
  const live = workspace.kind === "git" && workspace.state === "ready";
  const git = usePackGit(id, live);
  const ws = git.data?.workspace ?? workspace;
  const sha = live && ws.pr_number !== null ? ws.pushed_sha : null;
  const ci = usePackChecks(id, sha);
  const revision = usePackFilesRevision(id);

  // Правка после слияния снимает «принята»: у слитого запроса статус сам не опрашивается.
  useEffect(() => {
    if (revision === 0) return;
    void client.invalidateQueries({
      queryKey: [...packStudioKeys.workspace(id), "checks"],
      predicate: (query) =>
        (query.state.data as PackCiStatus | undefined)?.pr_state === "merged",
    });
  }, [revision, client, id]);

  return (sha !== null ? ci.data?.accepted_versions : undefined) ?? NONE;
};
