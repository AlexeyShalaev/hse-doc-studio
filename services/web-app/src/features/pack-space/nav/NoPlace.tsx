import { lazy, Suspense, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  PACK_STUDIO_PATH,
  spacePath,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import { useBootstrap } from "@entities/session";
import type { NewPackTarget } from "@features/pack-scaffold";
import { Button, EmptyState } from "@shared/ui";
import "../shell/space-shell.css";
import { CreateDialog } from "./CreateDialog";
import { WorkspaceBar } from "./SpaceBar";

// «Подключить официальные шаблоны»: то же окно, что в меню пространства; грузится по нажатию.
const ConnectCatalogDialog = lazy(() =>
  import("@features/pack-catalog-connect").then((m) => ({
    default: m.ConnectCatalogDialog,
  })),
);

/**
 * Пространство без версий (pack-studio-ux.md, 5.10): шапка пространства (назад, название, меню),
 * причина и один следующий шаг. Нет паков: «Создать пак» (в папке без репозитория рядом
 * «Подключить официальные шаблоны»); в паке нет шаблонов: «Создать шаблон»; у шаблона нет версий:
 * версию добавляют в репозитории, шаг здесь один: вернуться к списку.
 */
export const NoPlace = ({
  workspace,
  tree,
}: {
  workspace: PackWorkspace;
  tree: PackTree;
}) => {
  const workspaceId = workspace.id;
  const { t } = useTranslation("packSpace");
  const navigate = useNavigate();
  const isLocal = useBootstrap().data?.mode === "local";
  const [target, setTarget] = useState<NewPackTarget | null>(null);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const canConnect = workspace.kind !== "git" && isLocal;
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
    <div className="sp-root" data-testid="space-no-place">
      <header className="sp-bar" data-testid="sp-bar">
        <div className="sp-bar-lead">
          <WorkspaceBar
            workspace={workspace}
            navigate={(to, options) => {
              void navigate(to, options);
            }}
          />
        </div>
      </header>
      <div className="sp-grid">
        <section className="sp-center">
          <div className="sp-main">
            <EmptyState
              framed
              title={t(`nav.empty.${state.key}.title`, state.values)}
              description={t(`nav.empty.${state.key}.lead`)}
              action={
                state.action ? (
                  <div className="flex" style={{ gap: "0.5rem" }}>
                    <Button
                      onClick={() => {
                        setTarget(state.action);
                      }}
                      data-testid="space-no-versions-create"
                    >
                      {t(`nav.empty.${state.key}.action`)}
                    </Button>
                    {state.key === "noPacks" && canConnect ? (
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setCatalogOpen(true);
                        }}
                        data-testid="space-no-versions-official"
                      >
                        {t("nav.empty.official")}
                      </Button>
                    ) : null}
                  </div>
                ) : (
                  <Link className="btn sm" to={PACK_STUDIO_PATH}>
                    {t("shell.back")}
                  </Link>
                )
              }
              testId="space-no-versions"
            />
          </div>
        </section>
      </div>
      {catalogOpen ? (
        <Suspense fallback={null}>
          <ConnectCatalogDialog
            workspaceId={workspaceId}
            isOpen={catalogOpen}
            onClose={() => {
              setCatalogOpen(false);
            }}
          />
        </Suspense>
      ) : null}
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
