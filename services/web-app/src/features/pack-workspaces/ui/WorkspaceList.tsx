import { FolderGit2, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { packErrorText, usePackWorkspaces } from "@entities/pack-studio";
import { Button, EmptyState, ErrorState, Spinner } from "@shared/ui";
import { WorkspaceCard } from "./WorkspaceCard";

export type WorkspaceListProps = {
  onOpen: (id: string) => void;
  onCreate: () => void;
};

/** Рабочие пространства человека; пока идёт клон, список опрашивается сам. */
export const WorkspaceList = ({ onOpen, onCreate }: WorkspaceListProps) => {
  const { t } = useTranslation("packStudio");
  const list = usePackWorkspaces();
  if (list.isPending) {
    return (
      <div className="flex justify-center" style={{ padding: "2rem" }}>
        <Spinner size="md" />
      </div>
    );
  }
  if (list.isError) {
    return (
      <ErrorState
        description={packErrorText(list.error)}
        onRetry={() => void list.refetch()}
        retrying={list.isFetching}
        framed
      />
    );
  }
  if (list.data.length === 0) {
    return (
      <EmptyState
        framed
        icon={<FolderGit2 size="1.5rem" />}
        title={t("workspaces.emptyTitle")}
        description={t("workspaces.emptyLead")}
        action={
          <Button onClick={onCreate} data-testid="ws-create-empty">
            <Plus size="0.875rem" />
            {t("workspaces.create")}
          </Button>
        }
        testId="ws-empty"
      />
    );
  }
  return (
    <ul className="ps-ws-list" data-testid="ws-list">
      {list.data.map((workspace) => (
        <WorkspaceCard
          key={workspace.id}
          workspace={workspace}
          onOpen={onOpen}
        />
      ))}
    </ul>
  );
};
