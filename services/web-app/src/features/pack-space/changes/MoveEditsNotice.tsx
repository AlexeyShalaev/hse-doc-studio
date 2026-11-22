import { useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  PackErrorText,
  notifyPackFilesSaved,
  packStudioKeys,
  useMovePackVersionEdits,
  usePackFilesRevision,
  usePackVersionState,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Button, Spinner } from "@shared/ui";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";

/**
 * «Перенести правки в новую версию» (прежний `VersionBar`, template-studio.md, 7.3): каталог
 * выпущенной версии правили мимо Студии (в репозитории или в папке), он не совпадает с выпуском.
 * Правки уходят в копию следующего номера, Студия переходит в неё. Отчёт версии читается только
 * у открытой выпущенной версии; пока правок мимо Студии нет, блока нет.
 */
export const MoveEditsNotice = () => {
  const { t } = useTranslation("packSpace");
  const { workspace, versionRef, released } = useSpace();
  const id = workspace.id;
  const client = useQueryClient();
  const nav = useSpaceNav();
  const revision = usePackFilesRevision(id);
  const state = usePackVersionState(
    id,
    released ? versionRef : null,
    String(revision),
  );
  const move = useMovePackVersionEdits(id);
  const s = state.data;
  if (
    !released ||
    !s ||
    !s.released ||
    !s.modified ||
    s.version.version !== versionRef.version
  ) {
    return null;
  }
  const git = workspace.kind === "git";
  const target = s.move_to;
  const run = () => {
    move.mutate(
      { ref: s.version, version: target },
      {
        onSuccess: (moved) => {
          toast.success(
            t("changes.moveEdits.done", { version: moved.version.version }),
          );
          if (!moved.restored) toast.info(t("changes.moveEdits.notRestored"));
          notifyPackFilesSaved(id);
          void client
            .refetchQueries({ queryKey: packStudioKeys.tree(id) })
            .then(() => {
              nav.go({
                ref: {
                  pack: moved.version.pack,
                  template: moved.version.template,
                  version: moved.version.version,
                },
              });
            });
        },
      },
    );
  };
  return (
    <div
      className="sp-ch-banner"
      data-tone="warn"
      role="status"
      data-testid="sp-ch-move"
    >
      <TriangleAlert size="1rem" aria-hidden="true" />
      <div className="sp-ch-banner-text">
        <strong>
          {t("changes.moveEdits.title", { version: s.version.version })}
        </strong>
        <span>
          {target
            ? t(git ? "changes.moveEdits.leadGit" : "changes.moveEdits.lead", {
                version: target,
              })
            : t(
                git
                  ? "changes.moveEdits.leadGitAny"
                  : "changes.moveEdits.leadAny",
              )}
        </span>
        {move.isError && <PackErrorText error={move.error} />}
        <Button
          size="xs"
          variant="secondary"
          disabled={move.isPending}
          onClick={run}
          data-testid="sp-ch-move-submit"
        >
          {move.isPending && <Spinner size="sm" />}
          {target
            ? t("changes.moveEdits.button", { version: target })
            : t("changes.moveEdits.buttonAny")}
        </Button>
      </div>
    </div>
  );
};
