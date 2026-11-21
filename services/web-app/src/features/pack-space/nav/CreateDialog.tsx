import { lazy, Suspense } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  packStudioKeys,
  type PackScaffoldCreated,
  type PackVersionRef,
} from "@entities/pack-studio";
import type { NewPackTarget } from "@features/pack-scaffold";

// «Создать пак» и «Создать шаблон»: прежнее окно `pack-scaffold`, грузится по первому нажатию.
const NewPackDialog = lazy(() =>
  import("@features/pack-scaffold").then((m) => ({ default: m.NewPackDialog })),
);

/**
 * После создания дерево перечитывается и только потом открывается новая версия: иначе экран
 * не нашёл бы её в старом дереве и вернул бы на вход.
 */
export const CreateDialog = ({
  workspaceId,
  target,
  onClose,
  onOpen,
}: {
  workspaceId: string;
  target: NewPackTarget | null;
  onClose: () => void;
  onOpen: (ref: PackVersionRef) => void;
}) => {
  const client = useQueryClient();
  if (!target) return null;
  const opened = (created: PackScaffoldCreated) => {
    onClose();
    void client
      .refetchQueries({ queryKey: packStudioKeys.tree(workspaceId) })
      .then(() => {
        const { pack, template, version } = created.version;
        onOpen({ pack, template, version });
      });
  };
  return (
    <Suspense fallback={null}>
      <NewPackDialog
        workspaceId={workspaceId}
        target={target}
        onClose={onClose}
        onCreated={opened}
      />
    </Suspense>
  );
};
