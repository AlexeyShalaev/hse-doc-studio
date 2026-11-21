import { useEffect, useState, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  isJinjaPath,
  notifyPackFilesSaved,
  packStudioApi,
  packStudioKeys,
  versionDirOf,
  type PackFile,
} from "@entities/pack-studio";
import {
  FileAutosaver,
  type AutosaveSnapshot,
  type AutosaveOptions,
} from "./autosave";

export type AutosaveFile = AutosaveSnapshot & {
  edit: (text: string) => void;
  /** Записать сейчас. */
  flush: () => void;
  takeDisk: () => void;
  keepMine: () => void;
};

/**
 * Автосохранение открытого файла (pack-studio-ux.md, 5.5, срез S8b). Редактор пересоздаётся на
 * каждый файл (`key`), поэтому движок живёт ровно на один файл и при уходе дописывает хвост.
 * После записи обновляются кэш файла, подсказки версии, «Изменения» (git) и места подписей.
 */
export const useAutosaveFile = (
  workspaceId: string,
  file: PackFile,
  options: Pick<AutosaveOptions, "delayMs"> & { onWritten?: () => void } = {},
): AutosaveFile => {
  const client = useQueryClient();
  const [engine] = useState(
    () =>
      new FileAutosaver({
        initial: { content: file.content, etag: file.etag },
        ...(options.delayMs ? { delayMs: options.delayMs } : {}),
        write: (text, ifMatch) =>
          packStudioApi.writeFile(workspaceId, file.path, text, ifMatch),
        onWritten: (text, etag) => {
          client.setQueryData(packStudioKeys.file(workspaceId, file.path), {
            ...file,
            content: text,
            etag,
          });
          const versionDir = versionDirOf(file.path);
          if (
            versionDir &&
            (isJinjaPath(file.path) || /version\.yaml$/i.test(file.path))
          ) {
            void client.invalidateQueries({
              queryKey: packStudioKeys.hints(workspaceId, versionDir),
            });
          }
          void client.invalidateQueries({
            queryKey: packStudioKeys.git(workspaceId),
          });
          void client.invalidateQueries({
            queryKey: packStudioKeys.signaturesAll(workspaceId),
          });
          notifyPackFilesSaved(workspaceId);
          options.onWritten?.();
        },
      }),
  );
  const snapshot = useSyncExternalStore(engine.subscribe, engine.getSnapshot);
  useEffect(() => {
    engine.open();
    return () => {
      engine.close();
    };
  }, [engine]);
  return {
    ...snapshot,
    edit: (text) => {
      engine.edit(text);
    },
    flush: () => {
      void engine.flush();
    },
    takeDisk: () => {
      engine.takeDisk();
    },
    keepMine: () => {
      engine.keepMine();
    },
  };
};
