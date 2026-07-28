import { useLocation, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Bot, ChevronRight, GraduationCap, Lock, Settings } from "lucide-react";
import { clsx } from "clsx";
import { useSystemInfo } from "@entities/system";
import { useWorkspaceStore } from "@shared/lib";

export type AppTitlebarProps = {
  projectName?: string | null;
  projectIsNda?: boolean;
  /**
   * Слот на месте имени проекта в хлебных крошках. Страница проекта передаёт
   * сюда <ProjectSwitcher/>; остальные (welcome/мастер/настройки) не передают
   * ничего, и имя остаётся текстом. Слот, а не projectId, потому что виджету
   * запрещено импортировать другой виджет — композицию делает страница.
   */
  projectSwitcher?: React.ReactNode;
};

const Logomark = () => (
  <div
    className="flex items-center justify-center font-mono shrink-0"
    style={{
      width: 26,
      height: 26,
      borderRadius: 6,
      background:
        "linear-gradient(135deg, var(--accent), color-mix(in oklch, var(--accent) 60%, var(--fg-0) 0%))",
      color: "var(--accent-ink)",
      fontWeight: 700,
      fontSize: 12,
      letterSpacing: "-0.02em",
      boxShadow: "0 0 0 1px var(--accent-line)",
    }}
  >
    §
  </div>
);

export const AppTitlebar = ({
  projectName,
  projectIsNda,
  projectSwitcher,
}: AppTitlebarProps) => {
  const { t } = useTranslation("appChrome");
  const navigate = useNavigate();
  const location = useLocation();
  const systemChatOpen = useWorkspaceStore((state) => state.systemChatOpen);
  const toggleSystemChat = useWorkspaceStore((state) => state.toggleSystemChat);
  const { data: systemInfo } = useSystemInfo();

  // Real backend version; drop the suffix until it resolves rather than show a
  // stale hardcoded number.
  const versionLabel = systemInfo
    ? t("titlebar.version", { version: systemInfo.version })
    : t("titlebar.versionFallback");

  const isOnWelcome = !projectName;
  const settingsActive = location.pathname.startsWith("/settings");
  // The one agent adapts to context — its tooltip says so.
  const inProject = location.pathname.startsWith("/projects/");
  const agentTooltip = inProject
    ? t("titlebar.agentProject")
    : t("titlebar.agentAssistant");

  const handleBackToWelcome = () => {
    void navigate("/");
  };

  const handleOpenSettings = () => {
    void navigate("/settings");
  };

  return (
    <div className="titlebar">
      <button
        type="button"
        onClick={handleBackToWelcome}
        className="flex items-center shrink-0 cursor-pointer"
        style={{
          background: "transparent",
          border: 0,
          padding: 0,
          gap: 8,
          alignItems: "center",
        }}
      >
        <Logomark />
        <div className="flex flex-col items-start" style={{ gap: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: "-0.01em",
              color: "var(--fg-0)",
            }}
          >
            HSE Studio
          </div>
          <div
            className="mono"
            style={{
              fontSize: 9.5,
              color: "var(--fg-3)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              marginTop: -2,
            }}
          >
            {versionLabel}
          </div>
        </div>
      </button>

      <div
        className="flex items-center flex-1 min-w-0 overflow-hidden"
        style={{
          gap: 8,
          marginLeft: 26,
          color: "var(--fg-2)",
          fontSize: 12.5,
          alignItems: "center",
        }}
      >
        <button
          type="button"
          className="row-btn shrink-0"
          style={{
            width: "auto",
            padding: "5px 10px",
            color: isOnWelcome ? "var(--fg-0)" : "var(--fg-2)",
          }}
          onClick={handleBackToWelcome}
        >
          <GraduationCap size={15} />
          {t("titlebar.projects")}
        </button>
        {projectName && (
          <>
            <ChevronRight
              size={12}
              style={{ color: "var(--fg-3)", flexShrink: 0 }}
            />
            <div
              className="flex items-center min-w-0 overflow-hidden"
              style={{ gap: 8 }}
            >
              {projectSwitcher ?? (
                <span
                  className="truncate"
                  style={{ color: "var(--fg-0)", fontWeight: 500 }}
                >
                  {projectName}
                </span>
              )}
              {projectIsNda && (
                <span
                  className="chip shrink-0"
                  style={{
                    color: "var(--c-warn)",
                    borderColor:
                      "color-mix(in oklch, var(--c-warn) 30%, transparent)",
                  }}
                >
                  <Lock size={10} />
                  NDA
                </span>
              )}
            </div>
          </>
        )}
      </div>

      <div
        className="flex items-center shrink-0"
        style={{ gap: 4, alignItems: "center" }}
      >
        <button
          type="button"
          className={clsx("icon-btn tt", systemChatOpen && "active")}
          data-tt={agentTooltip}
          onClick={toggleSystemChat}
          style={
            systemChatOpen
              ? { width: 32, height: 32, color: "var(--accent)" }
              : { width: 32, height: 32 }
          }
        >
          <Bot size={16} />
        </button>

        <button
          type="button"
          className={clsx("icon-btn tt", settingsActive && "active")}
          data-tt={t("titlebar.settings")}
          onClick={handleOpenSettings}
          style={
            settingsActive
              ? { width: 32, height: 32, color: "var(--accent)" }
              : { width: 32, height: 32 }
          }
        >
          <Settings size={16} />
        </button>
      </div>
    </div>
  );
};
