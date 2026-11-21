import type { PackWorkspace } from "@entities/pack-studio";
import type { WorkspaceStatus } from "../lib/workspaceStatus";
import { WorkspaceCard } from "./WorkspaceCard";
import "./space-list.css";

export type WorkspaceListProps = {
  workspaces: readonly PackWorkspace[];
  statusOf: (workspace: PackWorkspace) => WorkspaceStatus;
  /** Пространство, у которого главная кнопка «Продолжить»; у остальных «Открыть». */
  continueId: string | null;
  onOpen: (id: string) => void;
};

/** Пространства человека; пока идёт подключение, список опрашивается сам (usePackWorkspaces). */
export const WorkspaceList = ({
  workspaces,
  statusOf,
  continueId,
  onOpen,
}: WorkspaceListProps) => (
  <ul className="sp-list" data-testid="ws-list">
    {workspaces.map((workspace) => (
      <WorkspaceCard
        key={workspace.id}
        workspace={workspace}
        status={statusOf(workspace)}
        isContinue={workspace.id === continueId}
        onOpen={onOpen}
      />
    ))}
  </ul>
);
