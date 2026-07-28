import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { SectionCard } from "../SectionCard";

export type ConfidentialitySectionProps = {
  isNda: boolean;
  // Владелец решает, надо ли спросить про удаление файлов НДА.
  onToggle: () => void;
};

export const ConfidentialitySection = ({
  isNda,
  onToggle,
}: ConfidentialitySectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionConfidentiality")}>
      <div
        className="flex items-center justify-between"
        style={{
          padding: 12,
          background: isNda ? "var(--c-warn-soft)" : "var(--bg-2)",
          borderRadius: "var(--r-2)",
          border:
            "1px solid " +
            (isNda
              ? "color-mix(in oklch, var(--c-warn) 30%, var(--border))"
              : "var(--border)"),
        }}
      >
        <div className="flex items-center gap-2">
          <Lock
            size={14}
            style={{ color: isNda ? "var(--c-warn)" : "var(--fg-2)" }}
          />
          <div className="flex flex-col" style={{ gap: 1 }}>
            <strong style={{ fontSize: 12.5 }}>
              {t("projectSettings.ndaTitle")}
            </strong>
            <span className="dim" style={{ fontSize: 11 }}>
              {t("projectSettings.ndaHint")}
            </span>
          </div>
        </div>
        <span className={clsx("toggle", isNda && "on")} onClick={onToggle} />
      </div>
    </SectionCard>
  );
};
