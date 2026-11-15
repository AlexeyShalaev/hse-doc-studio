import { useState } from "react";
import {
  Folder,
  FolderGit2,
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
import { formatRelativeTime } from "@shared/lib";
import { workspaceSource } from "../lib/workspaceSource";
import { ActionMenu, Badge, Button, Modal, Spinner } from "@shared/ui";

export type WorkspaceCardProps = {
  workspace: PackWorkspace;
  onOpen: (id: string) => void;
};

const KIND_ICON: Record<PackWorkspace["kind"], LucideIcon> = {
  git: FolderGit2,
  folder: Folder,
};

/** Состояние пространства одной меткой: клон идёт, не удался, выборка, готово. */
export const WorkspaceStateBadge = ({
  workspace,
}: {
  workspace: PackWorkspace;
}) => {
  const { t } = useTranslation("packStudio");
  if (workspace.state === "cloning") {
    return (
      <Badge variant="info" data-testid="ws-state-cloning">
        <Spinner size="sm" />
        {t("workspaces.state.cloning")}
      </Badge>
    );
  }
  if (workspace.state === "failed") {
    return (
      <Badge variant="error" data-testid="ws-state-failed">
        {t("workspaces.state.failed")}
      </Badge>
    );
  }
  if (workspace.busy) {
    return (
      <Badge variant="info" data-testid="ws-state-fetching">
        <Spinner size="sm" />
        {t("workspaces.state.fetching")}
      </Badge>
    );
  }
  return (
    <Badge variant="success" data-testid="ws-state-ready">
      {t("workspaces.state.ready")}
    </Badge>
  );
};

/** Карточка рабочего пространства в списке: источник, состояние, действия. */
export const WorkspaceCard = ({ workspace, onOpen }: WorkspaceCardProps) => {
  const { t } = useTranslation("packStudio");
  const refresh = useRefreshPackWorkspace();
  const remove = useDeletePackWorkspace();
  const [confirming, setConfirming] = useState(false);
  const Icon = KIND_ICON[workspace.kind];
  const ready = workspace.state === "ready";
  const git = workspace.kind === "git";
  const fetched = workspace.fetched_at
    ? t("workspaces.fetched", {
        when: formatRelativeTime(workspace.fetched_at),
      })
    : null;

  return (
    <li
      className="ps-ws-card"
      data-testid={`ws-card-${workspace.id}`}
      data-state={workspace.state}
    >
      <span className="ps-ws-icon" aria-hidden="true">
        <Icon size="1.125rem" />
      </span>
      <div className="ps-ws-body">
        <div className="ps-ws-title">
          <button
            type="button"
            className="ps-link truncate"
            disabled={!ready}
            onClick={() => {
              onOpen(workspace.id);
            }}
            data-testid="ws-open"
          >
            {workspace.label}
          </button>
          <WorkspaceStateBadge workspace={workspace} />
        </div>
        <div
          className="ps-ws-meta mono truncate"
          title={workspaceSource(workspace)}
        >
          {workspaceSource(workspace)}
        </div>
        <div className="ps-ws-meta">
          {t("workspaces.packsPath", { path: workspace.packs_path })}
          {fetched ? ` · ${fetched}` : ""}
        </div>
        {workspace.error && (
          <div
            className="ps-ws-error"
            role={workspace.state === "failed" ? "alert" : "status"}
            data-testid="ws-error"
          >
            {workspaceErrorText(workspace.error)}
          </div>
        )}
      </div>
      <div className="ps-ws-actions">
        {ready && (
          <Button
            size="sm"
            onClick={() => {
              onOpen(workspace.id);
            }}
          >
            {t("workspaces.open")}
          </Button>
        )}
        {git && workspace.state === "failed" && (
          <Button
            size="sm"
            variant="secondary"
            disabled={refresh.isPending}
            onClick={() => {
              refresh.mutate(workspace.id);
            }}
            data-testid="ws-retry"
          >
            <RefreshCw size="0.75rem" />
            {t("workspaces.retry")}
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
                    label: t("workspaces.refresh"),
                    icon: <RefreshCw size="0.875rem" />,
                    disabled: workspace.busy,
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
          <p className="ps-ws-error" role="alert">
            {packErrorText(remove.error)}
          </p>
        )}
      </Modal>
    </li>
  );
};
