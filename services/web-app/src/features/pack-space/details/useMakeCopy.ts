import { useQueryClient } from "@tanstack/react-query";
import {
  packStudioKeys,
  useCreatePackVersion,
  type PackVersionCreated,
} from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";

/**
 * «Править копию» выпущенной версии (pack-studio-ux.md, 5.3): черновик со следующим номером
 * создаётся без окна, человек остаётся на этом же экране: те же условия и тот же выбранный
 * элемент, только версия уже его собственная.
 */
export const useMakeCopy = () => {
  const { workspace, versionRef, selection } = useSpace();
  const nav = useSpaceNav();
  const client = useQueryClient();
  const create = useCreatePackVersion(workspace.id);
  const run = () => {
    create.mutate(
      {
        pack: versionRef.pack,
        template: versionRef.template,
        body: { base: versionRef.version, update_class: "patch" },
      },
      {
        onSuccess: (created: PackVersionCreated) => {
          // Дерево должно уже знать новую версию, иначе экран не найдёт её по адресу.
          void client
            .refetchQueries({ queryKey: packStudioKeys.tree(workspace.id) })
            .then(() => {
              nav.go({
                ref: {
                  pack: created.version.pack,
                  template: created.version.template,
                  version: created.version.version,
                },
                sel: selection,
              });
            });
        },
      },
    );
  };
  return { run, pending: create.isPending, error: create.error };
};
