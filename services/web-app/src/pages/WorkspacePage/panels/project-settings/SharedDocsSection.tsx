import { Files } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { SectionCard } from "../SectionCard";

export type SharedDocsSectionProps = {
  isEnabled: boolean;
  isPending: boolean;
  onToggle: () => void;
};

// Team-only: комплект общих документов проекта.
export const SharedDocsSection = ({
  isEnabled,
  isPending,
  onToggle,
}: SharedDocsSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionSharedDocs")}>
      {/* Тоггл живой: POST /team/sets. Выключение не удаляет файлы —
          общие документы лишь дерегистрируются (восстановимо). */}
      <div
        className="flex items-center justify-between"
        style={{
          padding: "0.75rem",
          background: "var(--bg-2)",
          borderRadius: "var(--r-2)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center gap-2">
          <Files
            size="0.875rem"
            style={{ color: isEnabled ? "var(--accent)" : "var(--fg-2)" }}
          />
          <div className="flex flex-col" style={{ gap: 1 }}>
            <strong style={{ fontSize: "0.78125rem" }}>
              {t("projectSettings.sharedDocsTitle")}
            </strong>
            <span className="dim" style={{ fontSize: "0.6875rem" }}>
              {t("projectSettings.sharedDocsHint")}
            </span>
          </div>
        </div>
        <button
          type="button"
          className={clsx("sev tt", isEnabled && "ok")}
          data-tt={
            isEnabled
              ? t("projectSettings.sharedDocsToggleOffHint")
              : t("projectSettings.sharedDocsToggleOnHint")
          }
          disabled={isPending}
          onClick={onToggle}
          style={{
            cursor: "pointer",
            opacity: isPending ? 0.6 : undefined,
            ...(isEnabled
              ? {}
              : {
                  color: "var(--fg-2)",
                  borderColor: "var(--border)",
                  background: "var(--bg-2)",
                }),
          }}
        >
          {isEnabled
            ? t("projectSettings.sharedDocsEnabled")
            : t("projectSettings.sharedDocsDisabled")}
        </button>
      </div>
    </SectionCard>
  );
};
