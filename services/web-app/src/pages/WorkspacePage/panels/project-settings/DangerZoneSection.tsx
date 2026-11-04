import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SectionCard } from "../SectionCard";

export type DangerZoneSectionProps = {
  isArchived: boolean;
  isRemoving: boolean;
  onToggleArchive: () => void;
  onUnlink: () => void;
  /** invites: блок «Передать проект» (только владельцу серверного проекта). */
  transferSlot?: React.ReactNode;
};

export const DangerZoneSection = ({
  isArchived,
  isRemoving,
  onToggleArchive,
  onUnlink,
  transferSlot,
}: DangerZoneSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard
      title={t("projectSettings.sectionDangerZone")}
      fullSpan
      accent="err"
    >
      {transferSlot}
      <div
        className="flex items-center justify-between"
        style={{
          padding: "0.75rem",
          border:
            "1px solid color-mix(in oklch, var(--c-err) 30%, var(--border))",
          borderRadius: "var(--r-2)",
        }}
      >
        <div className="flex flex-col" style={{ gap: "0.125rem" }}>
          <strong style={{ fontSize: "0.78125rem" }}>
            {t("projectSettings.archiveProject")}
          </strong>
          <span className="dim" style={{ fontSize: "0.6875rem" }}>
            {t("projectSettings.archiveProjectHint")}
          </span>
        </div>
        <button type="button" className="btn" onClick={onToggleArchive}>
          {isArchived
            ? t("projectSettings.restore")
            : t("projectSettings.archive")}
        </button>
      </div>
      <div
        className="flex items-center justify-between"
        style={{
          padding: "0.75rem",
          border:
            "1px solid color-mix(in oklch, var(--c-err) 30%, var(--border))",
          borderRadius: "var(--r-2)",
        }}
      >
        <div className="flex flex-col" style={{ gap: "0.125rem" }}>
          <strong style={{ fontSize: "0.78125rem" }}>
            {t("projectSettings.unlinkFromFolder")}
          </strong>
          <span className="dim" style={{ fontSize: "0.6875rem" }}>
            {t("projectSettings.unlinkFromFolderHint")}
          </span>
        </div>
        <button
          type="button"
          className="btn danger"
          disabled={isRemoving}
          onClick={onUnlink}
        >
          <Trash2 size="0.6875rem" />
          {t("projectSettings.unlink")}
        </button>
      </div>
    </SectionCard>
  );
};
