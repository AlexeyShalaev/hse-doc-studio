import { lazy, Suspense, useState } from "react";
import {
  ArrowLeft,
  FolderOpen,
  Library,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  PACK_STUDIO_PATH,
  packErrorText,
  useDeletePackWorkspace,
  usePackWorkspaces,
  useRefreshPackWorkspace,
  workspaceErrorText,
} from "@entities/pack-studio";
import { useBootstrap } from "@entities/session";
import {
  ActionMenu,
  Badge,
  Button,
  Modal,
  type ActionMenuItem,
} from "@shared/ui";
import { useSpace } from "../context/SpaceContext";
import "./space-nav.css";

// «Подключить к каталогу этой Студии»: окно и сущность каталога грузятся по первому нажатию.
const ConnectCatalogDialog = lazy(() =>
  import("@features/pack-catalog-connect").then((m) => ({
    default: m.ConnectCatalogDialog,
  })),
);

const MAX_OTHERS = 6;

/**
 * Левая часть верхней полосы: назад к списку, название пространства и меню «Ещё» (обновить,
 * переключить на другое, подключить к каталогу Студии, удалить). Всё про само пространство.
 */
export const SpaceBar = () => {
  const { t } = useTranslation("packSpace");
  const { workspace, location } = useSpace();
  const refresh = useRefreshPackWorkspace();
  const remove = useDeletePackWorkspace();
  const all = usePackWorkspaces();
  const isLocal = useBootstrap().data?.mode === "local";
  const [confirming, setConfirming] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const git = workspace.kind === "git";

  const others = (all.data ?? [])
    .filter((item) => item.id !== workspace.id && item.state === "ready")
    .slice(0, MAX_OTHERS);
  const items: ActionMenuItem[] = [
    ...(git
      ? [
          {
            id: "refresh",
            label: t("nav.bar.refresh"),
            icon: <RefreshCw size="0.875rem" aria-hidden="true" />,
            disabled: workspace.busy || refresh.isPending,
            testId: "sp-ws-refresh",
            onSelect: () => {
              refresh.mutate(workspace.id);
            },
          },
        ]
      : []),
    ...others.map((item) => ({
      id: `switch-${item.id}`,
      label: t("nav.bar.switchTo", { name: item.label }),
      icon: <FolderOpen size="0.875rem" aria-hidden="true" />,
      testId: `sp-ws-switch-${item.id}`,
      onSelect: () => {
        location.navigate(
          `${PACK_STUDIO_PATH}/w/${encodeURIComponent(item.id)}`,
        );
      },
    })),
    ...(!git && isLocal
      ? [
          {
            id: "catalog",
            label: t("nav.bar.connectCatalog"),
            icon: <Library size="0.875rem" aria-hidden="true" />,
            testId: "sp-ws-catalog",
            onSelect: () => {
              setCatalogOpen(true);
            },
          },
        ]
      : []),
    {
      id: "delete",
      label: t("nav.bar.delete"),
      icon: <Trash2 size="0.875rem" aria-hidden="true" />,
      danger: true,
      testId: "sp-ws-delete",
      onSelect: () => {
        setConfirming(true);
      },
    },
  ];

  return (
    <>
      <Link
        to={PACK_STUDIO_PATH}
        className="sp-back"
        aria-label={t("shell.back")}
        title={t("shell.back")}
        data-testid="sp-back"
      >
        <ArrowLeft size="0.9375rem" aria-hidden="true" />
        <span className="sp-hide-phone">{t("nav.bar.spaces")}</span>
      </Link>
      <span className="sp-bar-sep sp-hide-phone" aria-hidden="true">
        /
      </span>
      <h1 className="sp-ws-name truncate" data-testid="sp-ws-name">
        {workspace.label}
      </h1>
      <ActionMenu
        label={t("nav.bar.menu", { name: workspace.label })}
        testId="sp-ws-menu"
        items={items}
      />
      {workspace.error ? (
        <Badge
          variant="warning"
          role="status"
          title={workspaceErrorText(workspace.error)}
          data-testid="sp-ws-warn"
        >
          {t("nav.bar.refreshFailed")}
        </Badge>
      ) : null}
      <Modal
        isOpen={confirming}
        onClose={() => {
          setConfirming(false);
        }}
        title={t("nav.bar.deleteTitle", { name: workspace.label })}
        description={t(git ? "nav.bar.deleteGit" : "nav.bar.deleteFolder")}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setConfirming(false);
              }}
            >
              {t("nav.bar.cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              data-testid="sp-ws-delete-confirm"
              onClick={() => {
                remove.mutate(workspace.id, {
                  onSuccess: () => {
                    location.navigate(PACK_STUDIO_PATH, { replace: true });
                  },
                });
              }}
            >
              {t("nav.bar.delete")}
            </Button>
          </>
        }
      >
        {remove.isError ? (
          <p className="sp-bar-error" role="alert">
            {packErrorText(remove.error)}
          </p>
        ) : null}
      </Modal>
      {catalogOpen ? (
        <Suspense fallback={null}>
          <ConnectCatalogDialog
            workspaceId={workspace.id}
            isOpen={catalogOpen}
            onClose={() => {
              setCatalogOpen(false);
            }}
          />
        </Suspense>
      ) : null}
    </>
  );
};
