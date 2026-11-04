import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCapabilities } from "@entities/session";
import { SettingHead } from "./Setting";
import { LanguageToolImagesSection } from "./LanguageToolImagesSection";

export const ChecksSection = () => {
  const { t } = useTranslation("settings");
  const { lacks } = useCapabilities();
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
          gap: "0.625rem",
          padding: "0.625rem 0.75rem",
          border: "1px solid var(--border)",
          borderRadius: "var(--r-2)",
          background: "var(--bg-2)",
          marginBottom: "0.25rem",
        }}
      >
        <Info
          size="0.875rem"
          className="shrink-0"
          style={{ color: "var(--c-info)", marginTop: 1 }}
        />
        <div
          className="flex flex-col"
          style={{ gap: "0.25rem", fontSize: "0.75rem", lineHeight: 1.5 }}
        >
          <span style={{ color: "var(--fg-1)" }}>
            {t("checks.perDocumentHint")}
          </span>
        </div>
      </div>

      {!lacks("docker_ui") && <LanguageToolImagesSection />}
    </>
  );
};
