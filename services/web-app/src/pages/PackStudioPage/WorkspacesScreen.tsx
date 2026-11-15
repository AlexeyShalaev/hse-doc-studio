import { useState } from "react";
import { Plus } from "lucide-react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { packWorkspacePath } from "@entities/pack-studio";
import { useCapabilities } from "@entities/session";
import { FolderPickerModal } from "@features/folder-picker";
import {
  CreateWorkspaceDialog,
  WorkspaceList,
} from "@features/pack-workspaces";
import { Button } from "@shared/ui";

/** Начало Студии шаблонов: рабочие пространства и создание нового (4.1). */
export const WorkspacesScreen = () => {
  const { t } = useTranslation("packStudio");
  const navigate = useNavigate();
  const { has } = useCapabilities();
  const [creating, setCreating] = useState(false);
  // Папка на диске есть только там, где Студия видит файловую систему (локально).
  const allowFolder = has("fs_browse");
  const open = (id: string) => {
    void navigate(packWorkspacePath(id));
  };

  return (
    <div className="ps-page" data-testid="ps-workspaces">
      <header className="ps-page-head">
        <div className="ps-page-titles">
          <h1 className="ps-page-title">{t("title")}</h1>
          <p className="ps-page-lead">{t("lead")}</p>
        </div>
        <Button
          onClick={() => {
            setCreating(true);
          }}
          data-testid="ws-create"
        >
          <Plus size="0.875rem" />
          {t("workspaces.create")}
        </Button>
      </header>
      <WorkspaceList
        onOpen={open}
        onCreate={() => {
          setCreating(true);
        }}
      />
      <CreateWorkspaceDialog
        isOpen={creating}
        onClose={() => {
          setCreating(false);
        }}
        allowFolder={allowFolder}
        renderFolderPicker={
          allowFolder ? (props) => <FolderPickerModal {...props} /> : undefined
        }
        onCreated={(workspace) => {
          setCreating(false);
          open(workspace.id);
        }}
      />
    </div>
  );
};
