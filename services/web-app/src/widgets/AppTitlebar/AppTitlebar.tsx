import { useLocation, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Bot, ChevronRight, GraduationCap, Lock, Settings } from "lucide-react";
import { clsx } from "clsx";
import { AccountMenu } from "@features/account-menu";
import { GuestBadge, useGuest } from "@features/guest-session";
import { HelpButton } from "@features/help-center";
import { InboxBell } from "@features/inbox";
import { HelpMenu } from "@features/onboarding";
import { useBootstrap } from "@entities/session";
import { useSystemInfo } from "@entities/system";
import { useIsPhoneWidth, useWorkspaceStore } from "@shared/lib";

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
  /**
   * Слот справа, перед кнопкой агента: действия открытого проекта (синхронизация).
   * Так же, слотом, а не импортом: виджет не может подтянуть другой виджет.
   */
  projectActions?: React.ReactNode;
  /** Строка версии под логотипом. Админка прячет её: версия есть в её меню. */
  showVersion?: boolean;
};

const Logomark = () => (
  <div
    className="flex items-center justify-center font-mono shrink-0"
    style={{
      width: "1.625rem",
      height: "1.625rem",
      borderRadius: "0.375rem",
      background:
        "linear-gradient(135deg, var(--accent), color-mix(in oklch, var(--accent) 60%, var(--fg-0) 0%))",
      color: "var(--accent-ink)",
      fontWeight: 700,
      fontSize: "0.75rem",
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
  projectActions,
  showVersion = true,
}: AppTitlebarProps) => {
  const { t } = useTranslation("appChrome");
  const navigate = useNavigate();
  const location = useLocation();
  const systemChatOpen = useWorkspaceStore((state) => state.systemChatOpen);
  const toggleSystemChat = useWorkspaceStore((state) => state.toggleSystemChat);
  const { data: systemInfo } = useSystemInfo();
  // links: гостю по ссылке недоступны агент и настройки приложения; вместо меню аккаунта бейдж гостя.
  const isGuest = useGuest() !== null;
  // Телефон: люди, Студия и синхронизация уходят во вторую строку, в первой места им нет.
  const isPhone = useIsPhoneWidth();
  // Агент, настройки и справка уходят в меню аккаунта только там, где оно есть: в локальной Студии аккаунта нет,
  // и без этих кнопок в шапке до настроек на телефоне было бы не добраться.
  const bootstrap = useBootstrap().data;
  const accountMenu = bootstrap?.mode === "server" && bootstrap.user !== null;
  const secondary = accountMenu ? "titlebar-secondary" : undefined;

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
    <>
      <div className="titlebar">
        <button
          type="button"
          onClick={handleBackToWelcome}
          className="titlebar-brand flex items-center shrink-0 cursor-pointer"
          style={{
            background: "transparent",
            border: 0,
            padding: 0,
            gap: "0.5rem",
            alignItems: "center",
          }}
        >
          <Logomark />
          <div
            className="titlebar-brandtext flex flex-col items-start"
            style={{ gap: 0 }}
          >
            <div
              style={{
                fontSize: "0.8125rem",
                fontWeight: 600,
                letterSpacing: "-0.01em",
                color: "var(--fg-0)",
              }}
            >
              HSE Studio
            </div>
            {showVersion && (
              <div
                className="mono"
                style={{
                  fontSize: "0.59375rem",
                  color: "var(--fg-3)",
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  marginTop: "-0.125rem",
                }}
              >
                {versionLabel}
              </div>
            )}
          </div>
        </button>

        <div
          className="titlebar-crumbs flex items-center flex-1 min-w-0 overflow-hidden"
          style={{
            gap: "0.5rem",
            marginLeft: "1.625rem",
            color: "var(--fg-2)",
            fontSize: "0.78125rem",
            alignItems: "center",
          }}
        >
          <button
            type="button"
            className={clsx(
              "row-btn shrink-0",
              projectName && "titlebar-crumb-root",
            )}
            style={{
              width: "auto",
              padding: "0.3125rem 0.625rem",
              color: isOnWelcome ? "var(--fg-0)" : "var(--fg-2)",
            }}
            onClick={handleBackToWelcome}
            aria-label={t("titlebar.projects")}
          >
            <GraduationCap size="0.9375rem" />
            {/* Телефон: рядом с именем проекта остаётся значок, на главной подпись нужна как заголовок */}
            <span className={clsx(!isOnWelcome && "titlebar-crumb-label")}>
              {t("titlebar.projects")}
            </span>
          </button>
          {projectName && (
            <>
              <ChevronRight
                size="0.75rem"
                className="titlebar-crumb-root"
                style={{ color: "var(--fg-3)", flexShrink: 0 }}
              />
              <div
                className="flex items-center min-w-0 overflow-hidden"
                style={{ gap: "0.5rem" }}
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
                    <Lock size="0.625rem" />
                    NDA
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        <div
          className="flex items-center shrink-0"
          style={{ gap: "0.25rem", alignItems: "center" }}
        >
          {projectActions && !isPhone && (
            <div
              className="flex items-center shrink-0"
              style={{ marginRight: "0.25rem" }}
            >
              {projectActions}
            </div>
          )}
          {!isGuest && (
            <button
              type="button"
              className={clsx(
                "icon-btn tt",
                secondary,
                systemChatOpen && "active",
              )}
              data-tt={agentTooltip}
              data-tour="titlebar-agent"
              onClick={toggleSystemChat}
              style={
                systemChatOpen
                  ? { width: "2rem", height: "2rem", color: "var(--accent)" }
                  : { width: "2rem", height: "2rem" }
              }
            >
              <Bot size="1rem" />
            </button>
          )}

          {!isGuest && (
            <button
              type="button"
              className={clsx(
                "icon-btn tt",
                secondary,
                settingsActive && "active",
              )}
              data-tt={t("titlebar.settings")}
              data-tour="titlebar-settings"
              onClick={handleOpenSettings}
              style={
                settingsActive
                  ? { width: "2rem", height: "2rem", color: "var(--accent)" }
                  : { width: "2rem", height: "2rem" }
              }
            >
              <Settings size="1rem" />
            </button>
          )}
          {!isGuest && <InboxBell />}
          <span className={clsx(secondary, "contents")}>
            {isGuest ? <HelpButton /> : <HelpMenu />}
          </span>
          <span data-tour="titlebar-account" className="flex items-center">
            <AccountMenu />
          </span>
          <GuestBadge />
        </div>
      </div>
      {isPhone && projectActions && (
        <div className="titlebar-subrow" data-testid="titlebar-subrow">
          {projectActions}
        </div>
      )}
    </>
  );
};
