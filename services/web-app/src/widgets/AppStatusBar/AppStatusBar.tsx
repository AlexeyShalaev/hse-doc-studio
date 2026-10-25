import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { useAppSettings } from "@entities/app-settings";
import { useRunnerHealth } from "@entities/system";
import { useTemplateUpdateSignal } from "@features/template-update";
import { useUIStore } from "@shared/lib";

export type AppStatusBarProps = {
  /** Открытый проект: строка состояния подсказывает про обновление его шаблона. */
  projectId?: string;
};

export const AppStatusBar = ({ projectId }: AppStatusBarProps = {}) => {
  const { t } = useTranslation("appChrome");
  const togglePalette = useUIStore((state) => state.togglePaletteOpen);
  const { data: health, isError: healthIsError } = useRunnerHealth();
  const { data: settings } = useAppSettings();

  const dockerStatus: "running" | "stopped" =
    !healthIsError && health?.docker === "running" ? "running" : "stopped";
  const dockerDotClass =
    dockerStatus === "running" ? "dot live" : "dot pending";
  const dockerLabel =
    dockerStatus === "running"
      ? t("appStatusBar.dockerRunning")
      : t("appStatusBar.dockerStopped");

  const engine = settings?.default_engine ?? "xelatex";

  return (
    <div className="statusbar">
      <span className="seg-item">
        <span className={dockerDotClass} />
        docker · {dockerLabel}
      </span>

      <span className="flex-1" />

      {projectId && <TemplateUpdateSegment projectId={projectId} />}

      <span className="seg-item mono">{engine}</span>
      <span
        className="seg-item seg-clickable"
        role="button"
        tabIndex={0}
        title={t("appStatusBar.paletteTooltip")}
        onClick={togglePalette}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            togglePalette();
          }
        }}
      >
        ⌘K {t("appStatusBar.commands")}
      </span>
    </div>
  );
};

const TemplateUpdateSegment = ({ projectId }: { projectId: string }) => {
  const { t } = useTranslation("templateUpdate");
  const navigate = useNavigate();
  const { currentVersion, update, markers } =
    useTemplateUpdateSignal(projectId);
  if (!update && markers.length === 0) return null;

  const open = (): void => {
    void navigate(`/projects/${projectId}/project-settings/project`);
  };
  const isConflict = markers.length > 0;
  return (
    <span
      className="seg-item seg-clickable"
      role="button"
      tabIndex={0}
      title={
        isConflict
          ? t("templateUpdate:status.markersTooltip")
          : t("templateUpdate:status.updateTooltip")
      }
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
      style={{ color: isConflict ? "var(--c-err)" : "var(--accent)" }}
    >
      <span className={isConflict ? "dot err" : "dot live"} />
      {isConflict
        ? t("templateUpdate:status.markers", { count: markers.length })
        : t("templateUpdate:status.update", {
            from: currentVersion,
            to: update?.version.version ?? "",
          })}
    </span>
  );
};
