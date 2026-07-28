import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SettingHead } from "./Setting";
import { LanguageToolImagesSection } from "./LanguageToolImagesSection";

export const ChecksSection = () => {
  const { t } = useTranslation("settings");
  return (
    <>
      <SettingHead
        anchorId="checks"
        title={t("checks.title")}
        sub={t("checks.subtitle")}
      />
      <div
        className="flex items-start"
        style={{
          gap: 10,
          padding: "10px 12px",
          border: "1px solid var(--border)",
          borderRadius: "var(--r-2)",
          background: "var(--bg-2)",
          marginBottom: 4,
        }}
      >
        <Info
          size={14}
          className="shrink-0"
          style={{ color: "var(--c-info)", marginTop: 1 }}
        />
        <div
          className="flex flex-col"
          style={{ gap: 4, fontSize: 12, lineHeight: 1.5 }}
        >
          <span style={{ color: "var(--fg-1)" }}>
            {t("checks.perDocumentHint")}
          </span>
        </div>
      </div>

      <LanguageToolImagesSection />
    </>
  );
};
