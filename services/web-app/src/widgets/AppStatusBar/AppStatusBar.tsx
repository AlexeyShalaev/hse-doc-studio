import { useTranslation } from "react-i18next";
import { useAppSettings } from "@entities/app-settings";
import { useRunnerHealth } from "@entities/system";
import { useUIStore } from "@shared/lib";

export const AppStatusBar = () => {
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
