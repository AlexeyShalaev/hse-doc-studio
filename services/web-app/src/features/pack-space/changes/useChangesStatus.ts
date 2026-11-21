import { useQueries, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import {
  packStudioApi,
  packStudioKeys,
  usePackChecks,
  usePackFilesRevision,
  usePackGit,
  usePackVersionModel,
  versionRefOf,
  type PackLint,
} from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import {
  deriveChangesStatus,
  lintTargets,
  readNotes,
  type ChangesRaw,
} from "./deriveChangesStatus";
import type { ChangesStatus } from "./types";

/** Статус вместе с тем, из чего он собран: панель «Изменения» показывает и детали. */
export type ChangesData = {
  status: ChangesStatus;
  raw: ChangesRaw;
  /** Почему git не прочитался (при `status.load === "failed"`). */
  error: unknown;
  /** Перечитать git (повтор после сбоя). */
  retry: () => void;
};

/**
 * Данные для статуса изменений. Запросы (все через общий кэш `packStudioKeys`, поэтому две
 * копии хука, кнопка и панель, не удваивают их):
 *  - `git` всегда (для git-пространства): число файлов, отставание, ветка, запрос;
 *  - `checks` хостинга, если есть запрос на слияние;
 *  - линтер по изменённым местам (не больше трёх), если есть изменения;
 *  - модель открытой версии (заметки), если это черновик с правками.
 * Запись любого файла пространства (`notifyPackFilesSaved`) перечитывает git и модель; проверки
 * перезапрашиваются сами, у них ключ зависит от числа записей.
 */
export const useChangesData = (): ChangesData => {
  const { workspace, tree, versionRef } = useSpace();
  const client = useQueryClient();
  const id = workspace.id;
  const live = workspace.kind === "git" && workspace.state === "ready";
  const revision = usePackFilesRevision(id);

  const git = usePackGit(id, live);
  const refetchGit = git.refetch;
  const gitError: unknown = git.error;
  const data = git.data ?? null;
  const ws = data?.workspace ?? workspace;
  const hasRequest = live && ws.pr_number !== null;
  const ci = usePackChecks(id, hasRequest ? ws.pushed_sha : null);

  const changed = useMemo(() => data?.changed ?? [], [data]);
  const targets = useMemo(
    () => lintTargets(changed, versionRef),
    [changed, versionRef],
  );
  const lintResults = useQueries({
    queries: targets.map((target) => ({
      queryKey: packStudioKeys.lint(id, target, String(revision)),
      queryFn: (): Promise<PackLint> => packStudioApi.lint(id, target),
      placeholderData: (previous: PackLint | undefined) => previous,
      staleTime: Infinity,
    })),
  });
  const lintStamp = lintResults.map((r) => r.dataUpdatedAt).join();
  const lint = useMemo(
    () => lintResults.flatMap((r) => (r.data ? [r.data] : [])),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- метка ответов вместо нестабильного массива
    [lintStamp],
  );

  const released =
    tree.packs
      .find((pack) => pack.id === versionRef.pack)
      ?.templates.find((template) => template.id === versionRef.template)
      ?.versions.find((version) => version.version === versionRef.version)
      ?.released ?? false;
  const editsHere = changed.some((change) => {
    const ref = versionRefOf(change.path);
    return (
      ref?.pack === versionRef.pack &&
      ref.template === versionRef.template &&
      ref.version === versionRef.version
    );
  });
  const model = usePackVersionModel(
    id,
    live && !released && editsHere ? versionRef : null,
  );

  // Файл записан где угодно в пространстве: git и модель версии устарели.
  useEffect(() => {
    if (revision === 0) return;
    void client.invalidateQueries({ queryKey: packStudioKeys.git(id) });
    void client.invalidateQueries({
      queryKey: packStudioKeys.model(id, versionRef),
    });
  }, [revision, client, id, versionRef]);

  const raw = useMemo<ChangesRaw>(
    () => ({
      workspace,
      tree,
      open: versionRef,
      git: data,
      gitLoad: !live
        ? "ready"
        : git.isError
          ? "failed"
          : data
            ? "ready"
            : "loading",
      ci: ci.data ?? null,
      lint,
      notes: model.data ? readNotes(model.data.manifest.data) : null,
    }),
    [
      workspace,
      tree,
      versionRef,
      data,
      live,
      git.isError,
      ci.data,
      lint,
      model.data,
    ],
  );
  const status = useMemo(() => deriveChangesStatus(raw), [raw]);
  return useMemo(
    () => ({
      status,
      raw,
      error: gitError,
      retry: () => {
        void refetchGit();
      },
    }),
    [status, raw, gitError, refetchGit],
  );
};

/**
 * Состояние изменений пространства (pack-studio-ux.md, 4.3): один объект `ChangesStatus` для
 * кнопки «Изменения», панели и главной кнопки (S4). Правила сборки: `deriveChangesStatus`.
 */
export const useChangesStatus = (): ChangesStatus => useChangesData().status;
