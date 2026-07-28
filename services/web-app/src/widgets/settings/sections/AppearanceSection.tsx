import { Grid3x3, Monitor, Moon, Sun } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useThemeStore } from "@shared/lib";
import { useUpdateAppSettings } from "@entities/app-settings";
import type { Theme } from "@shared/lib";
import type { Lang } from "@shared/api";
import { Setting, SettingHead } from "./Setting";

export const AppearanceSection = () => {
  const { t } = useTranslation("settings");
  const theme = useThemeStore((s) => s.theme);
  const density = useThemeStore((s) => s.density);
  const lang = useThemeStore((s) => s.lang);
  const setTheme = useThemeStore((s) => s.setTheme);
  const setDensity = useThemeStore((s) => s.setDensity);
  const setLang = useThemeStore((s) => s.setLang);
  const { mutate: updateSettings } = useUpdateAppSettings();

  const applyTheme = (next: Theme) => {
    setTheme(next);
    updateSettings({ theme: next });
  };

  // Local store is the source of truth (instant, offline); also mirror the
  // choice to backend settings so the agent/response layer can read it.
  const applyLang = (next: Lang) => {
    setLang(next);
    updateSettings({ interface_language: next });
  };

  return (
    <>
      <SettingHead
        anchorId="appearance"
        title={t("appearance.title")}
        sub={t("appearance.subtitle")}
      />
      <Setting
        anchorId="appearance-theme"
        label={t("appearance.theme")}
        hint={t("appearance.themeHint")}
      >
        <div className="seg">
          <button
            type="button"
            className={clsx(theme === "system" && "active")}
            onClick={() => {
              applyTheme("system");
            }}
          >
            <Monitor size={11} />
            {t("appearance.themeSystem")}
          </button>
          <button
            type="button"
            className={clsx(theme === "dark" && "active")}
            onClick={() => {
              applyTheme("dark");
            }}
          >
            <Moon size={11} />
            Dark · Navy ink
          </button>
          <button
            type="button"
            className={clsx(theme === "light" && "active")}
            onClick={() => {
              applyTheme("light");
            }}
          >
            <Sun size={11} />
            Light · Paper
          </button>
          <button
            type="button"
            className={clsx(theme === "blueprint" && "active")}
            onClick={() => {
              applyTheme("blueprint");
            }}
          >
            <Grid3x3 size={11} />
            Blueprint
          </button>
        </div>
      </Setting>
      <Setting anchorId="appearance-density" label={t("appearance.density")}>
        <div className="seg">
          <button
            type="button"
            className={clsx(density === "comfortable" && "active")}
            onClick={() => {
              setDensity("comfortable");
            }}
          >
            {t("appearance.densityComfortable")}
          </button>
          <button
            type="button"
            className={clsx(density === "compact" && "active")}
            onClick={() => {
              setDensity("compact");
            }}
          >
            {t("appearance.densityCompact")}
          </button>
        </div>
      </Setting>
      <Setting anchorId="appearance-language" label={t("appearance.language")}>
        <div className="seg">
          <button
            type="button"
            className={clsx(lang === "ru" && "active")}
            onClick={() => {
              applyLang("ru");
            }}
          >
            {t("appearance.languageRu")}
          </button>
          <button
            type="button"
            className={clsx(lang === "en" && "active")}
            onClick={() => {
              applyLang("en");
            }}
          >
            {t("appearance.languageEn")}
          </button>
        </div>
      </Setting>
    </>
  );
};
