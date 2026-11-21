import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import {
  packStudioApi,
  packStudioKeys,
  usePackFilesRevision,
  usePackVersionState,
  type PackFileChange,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  MAX_SCAN_FILES,
  VERSION_FILE,
  baseDirOf,
  findSameFiles,
  freshCopyDir,
  sameManifest,
  scanCandidates,
} from "./copyEdits";

/**
 * Копия открытой версии, сверенная с основой: что в ней совпало (`same`) и что считается правкой
 * человека. `pending`: сверка ещё идёт, до её конца все файлы копии считаются нетронутыми, чтобы
 * счётчик не прыгал со «87» на «3».
 */
export type CopyScan = {
  dir: string;
  /** Версия, с которой сверяем; `null`: основы нет (первая версия шаблона), сверять не с чем. */
  base: string | null;
  same: ReadonlySet<string>;
  pending: boolean;
};

const NONE: ReadonlySet<string> = new Set<string>();

/**
 * Сверка копии с основой. Запросов нет, пока открытая версия не копия (её каталога нет в основной
 * ветке) или копия слишком велика (`MAX_SCAN_FILES`): тогда счёт идёт по git как раньше. Файлы
 * основы читаются один раз (выпущенная версия не меняется), файлы копии заново после каждой
 * записи (`revision`).
 */
export const useCopyScan = (
  workspaceId: string,
  changed: readonly PackFileChange[],
  open: PackVersionRef,
  enabled: boolean,
): CopyScan | null => {
  const client = useQueryClient();
  const revision = usePackFilesRevision(workspaceId);
  const dir = useMemo(
    () => (enabled ? freshCopyDir(changed, open) : null),
    [enabled, changed, open],
  );
  const stateQuery = usePackVersionState(
    workspaceId,
    dir ? open : null,
    String(revision),
  );
  const loaded = stateQuery.data;
  const base =
    loaded && loaded.version.version === open.version ? loaded.base : null;
  const stateReady =
    dir === null || (loaded?.version.version === open.version && !loaded.error);
  const candidates = useMemo(
    () => (dir ? scanCandidates(changed, dir) : []),
    [changed, dir],
  );
  const scannable =
    dir !== null &&
    base !== null &&
    candidates.length > 0 &&
    candidates.length <= MAX_SCAN_FILES;

  const scan = useQuery({
    queryKey: [
      ...packStudioKeys.workspace(workspaceId),
      "copy-same",
      dir,
      base,
      String(revision),
    ],
    enabled: scannable,
    staleTime: Infinity,
    placeholderData: (previous) => previous,
    queryFn: async (): Promise<Set<string>> => {
      if (dir === null || base === null) return new Set();
      const baseDir = baseDirOf(dir, base);
      const baseRef = { ...open, version: base };
      return findSameFiles(dir, baseDir, candidates, {
        draft: (path) =>
          packStudioApi
            .readFile(workspaceId, path)
            .then((file) => file.etag ?? file.content)
            .catch(() => null),
        base: (path) =>
          client
            .fetchQuery({
              queryKey: [
                ...packStudioKeys.workspace(workspaceId),
                "copy-base",
                path,
              ],
              staleTime: Infinity,
              queryFn: () =>
                packStudioApi
                  .readFile(workspaceId, path)
                  .then((file) => file.etag ?? file.content),
            })
            .catch(() => null),
        manifest: async () => {
          const [mine, source] = await Promise.all([
            packStudioApi.versionModel(workspaceId, open),
            packStudioApi.versionModel(workspaceId, baseRef),
          ]);
          return sameManifest(mine.manifest.data, source.manifest.data);
        },
      });
    },
  });

  return useMemo((): CopyScan | null => {
    if (dir === null) return null;
    // Сверять не с чем или копия слишком велика: всё, как отдал git.
    if (stateReady && !scannable) {
      return { dir, base, same: NONE, pending: false };
    }
    if (scan.data) {
      return { dir, base, same: scan.data, pending: false };
    }
    // Сверка идёт: всё, что нашёл git в каталоге копии, пока считаем нетронутым.
    const all = new Set(candidates);
    all.add(`${dir}/${VERSION_FILE}`);
    return { dir, base, same: all, pending: true };
  }, [dir, base, stateReady, scannable, scan.data, candidates]);
};
