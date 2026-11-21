import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { packFormKind, packStudioKeys } from "@entities/pack-studio";
import { PackFileEditor } from "@features/pack-file-editor";
import { setContentDirty } from "../contentGuard";
import { LegacyFormPane } from "./LegacyFormPane";

// ВРЕМЕННО (S8b): редактор файла прежнего интерфейса со своей кнопкой «Сохранить». Автосохранение
// (S8b) заменяет `extend/segment-text.tsx` и этот файл вместе с `contentGuard`.

export type LegacyFileEditorProps = {
  workspaceId: string;
  path: string;
  /** Кто спрашивает охрану несохранённого (`contentGuard`). */
  owner: string;
  at?: string | null;
  /** Открыть другой файл из «Проблем» и форм. */
  onOpenFile: (path: string) => void;
};

export const LegacyFileEditor = ({
  workspaceId,
  path,
  owner,
  at,
  onOpenFile,
}: LegacyFileEditorProps) => {
  const client = useQueryClient();
  const [epoch, setEpoch] = useState(0);
  useEffect(
    () => () => {
      setContentDirty(owner, false);
    },
    [owner],
  );
  return (
    <div className="sp-ct-editor" data-testid="ct-legacy-editor">
      <PackFileEditor
        key={path}
        workspaceId={workspaceId}
        path={path}
        lintEpoch={epoch}
        pointer={at ?? null}
        onSaved={() => {
          setEpoch((n) => n + 1);
          // Правка на диске: «Изменения» (git) и места подписей версии.
          void client.invalidateQueries({
            queryKey: packStudioKeys.git(workspaceId),
          });
          void client.invalidateQueries({
            queryKey: packStudioKeys.signaturesAll(workspaceId),
          });
        }}
        onOpenFile={(target) => {
          onOpenFile(target);
        }}
        onDirtyChange={(dirty) => {
          setContentDirty(owner, dirty);
        }}
        form={
          packFormKind(path) ? (
            <LegacyFormPane
              workspaceId={workspaceId}
              path={path}
              at={at ?? null}
              onOpenFile={onOpenFile}
            />
          ) : undefined
        }
      />
    </div>
  );
};
