import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ProjectCreateWizard } from "@features/project-create";
import { ProjectConnectWizard } from "@features/project-connect";
import { useWorkspaceStore } from "@shared/lib";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { ChatDock } from "@widgets/ChatDock";

export const WizardPage = () => {
  const { t } = useTranslation("appChrome");
  const [searchParams] = useSearchParams();
  const mode = searchParams.get("mode") ?? "create";
  // The one unified agent, docked between the title and status bars. No project
  // exists yet here, so it runs with app/system tools (no project context).
  const systemChatOpen = useWorkspaceStore((state) => state.systemChatOpen);
  const toggleSystemChat = useWorkspaceStore((state) => state.toggleSystemChat);

  const projectLabel =
    mode === "create"
      ? t("wizardPage.createTitle")
      : t("wizardPage.connectTitle");

  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar projectName={projectLabel} />

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-hidden">
          {mode === "create" ? (
            <ProjectCreateWizard />
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
