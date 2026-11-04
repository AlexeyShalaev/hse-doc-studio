import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import { FontBrowser } from "./FontBrowser";
import { InstalledFontsList } from "./InstalledFontsList";
import { SettingHead } from "./Setting";

export const FontsSection = () => {
  const { t } = useTranslation("settings");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <SettingHead
        anchorId="fonts"
        title={t("fonts.title")}
        sub={t("fonts.subtitle")}
      />

      <div
        className="flex"
        style={{
          gap: "0.5rem",
          padding: "0.5625rem 0.6875rem",
          borderRadius: "0.375rem",
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
          fontSize: "0.71875rem",
          color: "var(--fg-2)",
          lineHeight: 1.5,
        }}
      >
        <Info
          size="0.875rem"
          style={{
            color: "var(--c-info, var(--accent))",
            flexShrink: 0,
            marginTop: 1,
          }}
        />
        <span>{t("fonts.info")}</span>
      </div>

      <InstalledFontsList />

      {/* Add fonts: pick a source — Google Fonts, the OS, or your own files. */}
      <FontBrowser />
    </div>
  );
};
