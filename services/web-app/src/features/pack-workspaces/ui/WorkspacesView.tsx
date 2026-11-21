import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  usePackOfficial,
  usePackWorkspaces,
  type PackWorkspace,
} from "@entities/pack-studio";
import { ErrorState, Spinner } from "@shared/ui";
import { availableConnectKinds, type ConnectKind } from "../lib/connectKinds";
import { useWorkspaceGit } from "../lib/useWorkspaceGit";
import {
  pickContinueId,
  workspaceStatus,
  type WorkspaceStatus,
} from "../lib/workspaceStatus";
import { ConnectButton, ConnectPaths } from "./ConnectPaths";
import {
  CreateWorkspaceDialog,
  type FolderPickerRender,
} from "./CreateWorkspaceDialog";
import { OfficialPacksDialog } from "./OfficialPacks";
import { WorkspaceList } from "./WorkspaceList";
import "./space-list.css";

export type WorkspacesViewProps = {
  onOpen: (id: string) => void;
  /** Папка на диске есть только там, где Студия видит файловую систему (локально). */
  allowFolder: boolean;
  renderFolderPicker?: FolderPickerRender | undefined;
  /** Пространство, которое человек открывал последним: от него зависит «Продолжить». */
  lastOpenedId?: string | null | undefined;
};

/**
 * Вход в Студию шаблонов (pack-studio-ux.md, 5.1): заголовок, список пространств
 * с одной главной кнопкой и подключение. Пусто: три пути подключения вместо списка.
 */
export const WorkspacesView = ({
  onOpen,
  allowFolder,
  renderFolderPicker,
  lastOpenedId = null,
}: WorkspacesViewProps) => {
  const { t } = useTranslation("packStudio");
  const list = usePackWorkspaces();
  const official = usePackOfficial();
  const workspaces = list.data ?? [];
  const gitById = useWorkspaceGit(workspaces);
  const [connecting, setConnecting] = useState<ConnectKind | null>(null);

  const open = (id: string) => {
    onOpen(id);
  };
  const officialData = official.data;
  const kinds = availableConnectKinds({
    // Официальные шаблоны уже подключены: пространство в списке.
    officialAvailable:
      officialData?.repo != null && officialData.workspace_id == null,
    allowFolder,
  });
  const continueId = pickContinueId(workspaces, gitById, lastOpenedId);
  const statusOf = (workspace: PackWorkspace): WorkspaceStatus =>
    workspaceStatus(workspace, gitById.get(workspace.id));
  const empty = list.data !== undefined && workspaces.length === 0;

  let body;
  if (list.isPending) {
    body = (
      <div
        className="flex justify-center"
        style={{ padding: "2rem" }}
        role="status"
        aria-label={t("workspaces.loading")}
      >
        <Spinner size="md" />
      </div>
    );
  } else if (list.isError && list.data === undefined) {
    // Фоновое обновление не удалось, но список уже есть: его не прячем.
    body = (
      <ErrorState
        description={packErrorText(list.error)}
        onRetry={() => void list.refetch()}
        retrying={list.isFetching}
        framed
      />
    );
  } else if (empty) {
    body = <ConnectPaths kinds={kinds} onConnect={setConnecting} />;
  } else {
    body = (
      <WorkspaceList
        workspaces={workspaces}
        statusOf={statusOf}
        continueId={continueId}
        onOpen={open}
      />
    );
  }

  return (
    <div className="ps-page" data-testid="ps-workspaces">
      <header className="ps-page-head">
        <div className="ps-page-titles">
          <h1 className="ps-page-title">{t("title")}</h1>
          <p
            className="ps-page-lead"
            data-testid={empty ? "ws-empty-lead" : "ws-lead"}
          >
            {empty ? t("connect.lead") : t("lead")}
          </p>
        </div>
        {list.data !== undefined && !empty && (
          <ConnectButton
            kinds={kinds}
            onConnect={setConnecting}
            primary={continueId === null}
          />
        )}
      </header>
      <div data-testid={empty ? "ws-empty" : undefined}>{body}</div>
      {connecting === "git" || connecting === "folder" ? (
        <CreateWorkspaceDialog
          isOpen
          kind={connecting}
          onClose={() => {
            setConnecting(null);
          }}
          allowServiceAccess={!allowFolder}
          renderFolderPicker={
            connecting === "folder" ? renderFolderPicker : undefined
          }
          onCreated={(workspace) => {
            setConnecting(null);
            open(workspace.id);
          }}
        />
      ) : null}
      {officialData?.repo != null && (
        <OfficialPacksDialog
          official={officialData}
          isOpen={connecting === "official"}
          onClose={() => {
            setConnecting(null);
          }}
          onOpened={(workspace) => {
            setConnecting(null);
            open(workspace.id);
          }}
        />
      )}
    </div>
  );
};
