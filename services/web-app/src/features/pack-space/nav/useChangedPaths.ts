import { useMemo } from "react";
import { usePackGit } from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";

const NONE: readonly string[] = [];

/**
 * Файлы, которыми пространство отличается от основной ветки: нужны, чтобы найти версию с моими
 * изменениями. Тот же запрос и тот же кэш, что у панели «Изменений»: лишних запросов нет.
 * В папке на диске git нет: изменений для навигации нет.
 */
export const useChangedPaths = (): readonly string[] => {
  const { workspace } = useSpace();
  const git = usePackGit(workspace.id, workspace.kind === "git");
  const changed = git.data?.changed;
  return useMemo(
    () => (changed ? changed.map((file) => file.path) : NONE),
    [changed],
  );
};
