import { useSearchParams, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { CloneWizard, type CloneFolderSlot } from "@features/git-remote";
import { FolderPickerModal, useInspectFolder } from "@features/folder-picker";
import { ProjectCreateWizard } from "@features/project-create";
import { ProjectConnectWizard } from "@features/project-connect";
import { readCloneTarget } from "@entities/git-sync";
import { useWorkspaceStore } from "@shared/lib";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { ChatDock } from "@widgets/ChatDock";

// Мастер клонирования не знает про фичу выбора папки (фичи друг друга не
// импортируют): окно выбора и проверку папки передаёт страница.
const useInspectCloneFolder: CloneFolderSlot["useInspect"] = (path) => {
  const query = useInspectFolder(path, path !== "");
  if (path === "") return { state: "idle" };
  if (query.isError) return { state: "unavailable" };
  if (!query.data) return { state: "checking" };
  return {
    state: "ready",
    exists: query.data.exists,
    isDir: query.data.is_dir,
    hasProject: query.data.has_project,
    projectName: query.data.project?.name ?? null,
  };
};

const CLONE_FOLDER_SLOT: CloneFolderSlot = {
  Picker: FolderPickerModal,
  useInspect: useInspectCloneFolder,
};

export const WizardPage = () => {
  const { t } = useTranslation("appChrome");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const mode = searchParams.get("mode") ?? "create";
  // The one unified agent, docked between the title and status bars. No project
  // exists yet here, so it runs with app/system tools (no project context).
  const systemChatOpen = useWorkspaceStore((state) => state.systemChatOpen);
  const toggleSystemChat = useWorkspaceStore((state) => state.toggleSystemChat);

  const projectLabel =
    mode === "create"
      ? t("wizardPage.createTitle")
      : mode === "clone"
        ? t("wizardPage.cloneTitle")
        : t("wizardPage.connectTitle");

  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar projectName={projectLabel} />

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-hidden">
          {mode === "create" ? (
            <ProjectCreateWizard />
          ) : mode === "clone" ? (
            <CloneWizard
              folderSlot={CLONE_FOLDER_SLOT}
              initialTarget={readCloneTarget(searchParams)}
              onExit={() => {
                void navigate("/");
              }}
              onOpenProject={(projectId) => {
                void navigate(`/projects/${projectId}/documents`);
              }}
            />
          ) : (
            <ProjectConnectWizard />
          )}
        </div>

        {systemChatOpen && <ChatDock onClose={toggleSystemChat} />}
      </div>

      <AppStatusBar />
    </div>
  );
};
