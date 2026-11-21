import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  PACK_STUDIO_PATH,
  spacePath,
  type PackTree,
} from "@entities/pack-studio";
import type { NewPackTarget } from "@features/pack-scaffold";
import { Button, EmptyState } from "@shared/ui";
import { CreateDialog } from "./CreateDialog";

/**
 * Пространство без версий (pack-studio-ux.md, 5.10): причина и один следующий шаг. Нет паков:
 * «Создать пак»; в паке нет шаблонов: «Создать шаблон»; у шаблона нет версий: версию добавляют
 * в репозитории, шаг здесь один: вернуться к списку.
 */
export const NoPlace = ({
  workspaceId,
  tree,
}: {
  workspaceId: string;
  tree: PackTree;
}) => {
  const { t } = useTranslation("packSpace");
  const navigate = useNavigate();
  const [target, setTarget] = useState<NewPackTarget | null>(null);
  const bare = tree.packs.find((pack) => pack.templates.length === 0);
  const hollow = tree.packs
    .flatMap((pack) => pack.templates)
    .find((template) => template.versions.length === 0);

  const state =
    tree.packs.length === 0
      ? {
          key: "noPacks",
          values: {},
          action: { kind: "pack" } satisfies NewPackTarget,
        }
      : bare
        ? {
            key: "noTemplates",
            values: { pack: bare.id },
            action: {
              kind: "template",
              pack: bare.path.split("/")[0] ?? bare.id,
            } satisfies NewPackTarget,
          }
        : {
            key: "noVersions",
            values: { template: hollow?.id ?? "" },
            action: null,
          };

  return (
    <div className="ps-page">
      <EmptyState
        framed
        title={t(`nav.empty.${state.key}.title`, state.values)}
        description={t(`nav.empty.${state.key}.lead`)}
        action={
          state.action ? (
            <Button
              onClick={() => {
                setTarget(state.action);
              }}
              data-testid="space-no-versions-create"
            >
              {t(`nav.empty.${state.key}.action`)}
            </Button>
          ) : (
            <Link className="btn sm" to={PACK_STUDIO_PATH}>
              {t("shell.back")}
            </Link>
          )
        }
        testId="space-no-versions"
      />
      <CreateDialog
        workspaceId={workspaceId}
        target={target}
        onClose={() => {
          setTarget(null);
        }}
        onOpen={(ref) => {
          void navigate(spacePath(workspaceId, ref, "result"), {
            replace: true,
          });
        }}
      />
    </div>
  );
};
