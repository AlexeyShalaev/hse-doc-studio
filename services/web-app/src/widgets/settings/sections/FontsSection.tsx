import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import { FontBrowser } from "./FontBrowser";
import { InstalledFontsList } from "./InstalledFontsList";
import { SettingHead } from "./Setting";

export const FontsSection = () => {
  const { t } = useTranslation("settings");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <SettingHead
        anchorId="fonts"
        title={t("fonts.title")}
        sub={t("fonts.subtitle")}
      />

      <div
        className="flex"
        style={{
          gap: 8,
          padding: "9px 11px",
          borderRadius: 6,
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
          fontSize: 11.5,
          color: "var(--fg-2)",
          lineHeight: 1.5,
        }}
      >
        <Info
          size={14}
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
