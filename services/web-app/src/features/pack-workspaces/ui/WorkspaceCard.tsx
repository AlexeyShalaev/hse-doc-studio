import { useState } from "react";
import {
  Check,
  Folder,
  FolderGit2,
  GitPullRequestArrow,
  RefreshCw,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useDeletePackWorkspace,
  useRefreshPackWorkspace,
  workspaceErrorText,
  type PackWorkspace,
} from "@entities/pack-studio";
import { RepoAccessDialog } from "@features/pack-git";
import { ActionMenu, Badge, Button, Modal, Spinner } from "@shared/ui";
import { shortUrl } from "../lib/workspaceSource";
import type { WorkspaceStatus } from "../lib/workspaceStatus";
import "./space-list.css";

export type WorkspaceCardProps = {
  workspace: PackWorkspace;
  status: WorkspaceStatus;
  /** Сюда человек возвращается: у этой карточки главная кнопка «Продолжить». */
  isContinue: boolean;
  onOpen: (id: string) => void;
};

const KIND_ICON: Record<PackWorkspace["kind"], LucideIcon> = {
  git: FolderGit2,
  folder: Folder,
};

/** Состояние пространства словами (5.10): что с подключением, запросом и правками. */
export const WorkspaceStatusBadges = ({
  status,
}: {
  status: WorkspaceStatus;
}) => {
  const { t } = useTranslation("packStudio");
  switch (status.kind) {
    case "cloning":
      return (
        <Badge variant="info" data-testid="ws-status-cloning">
          <Spinner size="sm" />
          {t("workspaces.status.cloning")}
        </Badge>
      );
    case "fetching":
      return (
        <Badge variant="info" data-testid="ws-status-fetching">
          <Spinner size="sm" />
          {t("workspaces.status.fetching")}
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="error" data-testid="ws-status-failed">
          {t("workspaces.status.failed")}
        </Badge>
      );
    case "folder":
      return (
        <Badge variant="subtle" data-testid="ws-status-folder">
          {t("workspaces.status.folder")}
        </Badge>
      );
    case "request":
      return (
        <span className="sp-ws-badges">
          <Badge variant="accent" data-testid="ws-status-request">
            <GitPullRequestArrow size="0.6875rem" aria-hidden="true" />
            {t("workspaces.status.request", { number: status.number })}
          </Badge>
          {status.unsent > 0 && (
            <Badge variant="warning" data-testid="ws-status-unsent">
              {t("workspaces.status.newUnsent", { count: status.unsent })}
            </Badge>
          )}
        </span>
      );
    case "unsent":
      return (
        <Badge variant="warning" data-testid="ws-status-unsent">
          {t("workspaces.status.unsent", { count: status.unsent })}
        </Badge>
      );
    case "clean":
      return (
        <Badge variant="success" data-testid="ws-status-clean">
          <Check size="0.6875rem" aria-hidden="true" />
          {t("workspaces.status.clean")}
        </Badge>
      );
    case "unknown":
      return null;
  }
};

/** Вторая строка карточки: откуда пространство (5.1). */
const SourceLine = ({ workspace }: { workspace: PackWorkspace }) => {
  const { t } = useTranslation("packStudio");
  if (workspace.kind === "folder") {
    return <>{workspace.folder ?? ""}</>;
  }
  const parts = [
    workspace.official ? t("workspaces.sourceOfficial") : null,
    shortUrl(workspace.url ?? ""),
    // Основная ветка нужна, когда пространство уже работает: у неудачного её нет смысла показывать.
    workspace.state === "ready" && workspace.base_branch
      ? t("workspaces.baseBranch", { branch: workspace.base_branch })
      : null,
  ];
  return <>{parts.filter(Boolean).join(" · ")}</>;
};

/**
 * Карточка пространства в списке: название, состояние словами, откуда оно и одно
 * действие, зависящее от состояния («Продолжить», «Открыть», «Проверить доступ»).
 */
export const WorkspaceCard = ({
  workspace,
  status,
  isContinue,
  onOpen,
}: WorkspaceCardProps) => {
  const { t } = useTranslation("packStudio");
  const refresh = useRefreshPackWorkspace();
  const remove = useDeletePackWorkspace();
  const [confirming, setConfirming] = useState(false);
  const [checking, setChecking] = useState(false);
  const Icon = KIND_ICON[workspace.kind];
  const ready = workspace.state === "ready";
  const failed = workspace.state === "failed";
  const git = workspace.kind === "git";
  const source = workspace.kind === "git" ? (workspace.url ?? "") : "";

  const closeAccess = () => {
    setChecking(false);
    // Токен могли поменять: подключение пробуется заново.
    if (failed && git) refresh.mutate(workspace.id);
  };

  return (
    <li
      className="sp-ws"
      data-testid={`ws-card-${workspace.id}`}
      data-state={workspace.state}
    >
      <span className="sp-ws-ico" aria-hidden="true">
        <Icon size="1.25rem" />
      </span>
      <div className="sp-ws-body">
        <div className="sp-ws-title">
          <button
            type="button"
            className="sp-ws-name"
            disabled={!ready}
            onClick={() => {
              onOpen(workspace.id);
            }}
            data-testid="ws-open"
          >
            {workspace.label}
          </button>
          <WorkspaceStatusBadges status={status} />
        </div>
        <div className="sp-ws-meta" title={source || undefined}>
          <SourceLine workspace={workspace} />
        </div>
        {workspace.error && (
          <p
            className="sp-ws-err"
            role={failed ? "alert" : "status"}
            data-testid="ws-error"
          >
            {workspaceErrorText(workspace.error)}
          </p>
        )}
        {failed && (
          <p className="sp-ws-meta" data-testid="ws-failed-hint">
            {t("workspaces.failedHint")}
          </p>
        )}
      </div>
      <div className="sp-ws-acts">
        {workspace.state === "cloning" && (
          <span className="sp-ws-wait" data-testid="ws-wait">
            {t("workspaces.cloningHint")}
          </span>
        )}
        {ready && (
          <Button
            size="sm"
            variant={isContinue ? "primary" : "secondary"}
            onClick={() => {
              onOpen(workspace.id);
            }}
            data-testid={isContinue ? "ws-continue" : "ws-open-button"}
          >
            {isContinue ? t("workspaces.continue") : t("workspaces.open")}
          </Button>
        )}
        {failed && git && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setChecking(true);
            }}
            data-testid="ws-check-access"
          >
            {t("workspaces.checkAccess")}
          </Button>
        )}
        <ActionMenu
          label={t("workspaces.actions", { name: workspace.label })}
          testId="ws-menu"
          items={[
            ...(git && ready
              ? [
                  {
                    id: "refresh",
                    label: t("workspaces.menuRefresh"),
                    icon: <RefreshCw size="0.875rem" />,
                    disabled: workspace.busy,
                    onSelect: () => {
                      refresh.mutate(workspace.id);
                    },
                  },
                ]
              : []),
            ...(git && failed
              ? [
                  {
                    id: "retry",
                    label: t("workspaces.retryConnect"),
                    icon: <RefreshCw size="0.875rem" />,
                    disabled: refresh.isPending,
                    testId: "ws-retry",
                    onSelect: () => {
                      refresh.mutate(workspace.id);
                    },
                  },
                ]
              : []),
            {
              id: "delete",
              label: t("workspaces.delete"),
              icon: <Trash2 size="0.875rem" />,
              danger: true,
              testId: "ws-delete",
              onSelect: () => {
                setConfirming(true);
              },
            },
          ]}
        />
      </div>
      {git && failed && (
        <RepoAccessDialog
          workspace={workspace}
          isOpen={checking}
          onClose={closeAccess}
        />
      )}
      <Modal
        isOpen={confirming}
        onClose={() => {
          setConfirming(false);
        }}
        title={t("workspaces.deleteTitle", { name: workspace.label })}
        description={
          git ? t("workspaces.deleteGitHint") : t("workspaces.deleteFolderHint")
        }
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setConfirming(false);
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              data-testid="ws-delete-confirm"
              onClick={() => {
                remove.mutate(workspace.id, {
                  onSuccess: () => {
                    setConfirming(false);
                  },
                });
              }}
            >
              {t("workspaces.delete")}
            </Button>
          </>
        }
      >
        {remove.isError && (
          <p className="sp-ws-err" role="alert">
            {packErrorText(remove.error)}
          </p>
        )}
      </Modal>
    </li>
  );
};
