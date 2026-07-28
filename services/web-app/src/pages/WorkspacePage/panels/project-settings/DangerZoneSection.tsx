import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SectionCard } from "../SectionCard";

export type DangerZoneSectionProps = {
  isArchived: boolean;
  isRemoving: boolean;
  onToggleArchive: () => void;
  onUnlink: () => void;
};

export const DangerZoneSection = ({
  isArchived,
  isRemoving,
  onToggleArchive,
  onUnlink,
}: DangerZoneSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard
      title={t("projectSettings.sectionDangerZone")}
      fullSpan
      accent="err"
    >
      <div
        className="flex items-center justify-between"
        style={{
          padding: 12,
          border:
            "1px solid color-mix(in oklch, var(--c-err) 30%, var(--border))",
          borderRadius: "var(--r-2)",
        }}
      >
        <div className="flex flex-col" style={{ gap: 2 }}>
          <strong style={{ fontSize: 12.5 }}>
            {t("projectSettings.archiveProject")}
          </strong>
          <span className="dim" style={{ fontSize: 11 }}>
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
          padding: 12,
          border:
            "1px solid color-mix(in oklch, var(--c-err) 30%, var(--border))",
          borderRadius: "var(--r-2)",
        }}
      >
        <div className="flex flex-col" style={{ gap: 2 }}>
          <strong style={{ fontSize: 12.5 }}>
            {t("projectSettings.unlinkFromFolder")}
          </strong>
          <span className="dim" style={{ fontSize: 11 }}>
            {t("projectSettings.unlinkFromFolderHint")}
          </span>
        </div>
        <button
          type="button"
          className="btn danger"
          disabled={isRemoving}
          onClick={onUnlink}
        >
          <Trash2 size={11} />
          {t("projectSettings.unlink")}
        </button>
      </div>
    </SectionCard>
  );
};
