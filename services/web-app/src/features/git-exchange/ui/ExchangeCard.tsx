import { useState, type ReactNode } from "react";
import { FileDown, FileUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSyncStatus } from "@entities/git-sync";
import { BundleExportDialog } from "./BundleExportDialog";
import { BundleImportDialog } from "./BundleImportDialog";

export type ExchangeCardProps = {
  projectId: string;
  /** Карточка лежит в окне: из импорта человека уводят дальше, окно надо закрыть. */
  onNavigate?: () => void;
};

const ActionRow = ({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  action: ReactNode;
}) => (
  <div
    className="flex items-center"
    style={{
      gap: 14,
      padding: 12,
      borderRadius: "var(--r-2)",
      background: "var(--bg-2)",
      flexWrap: "wrap",
    }}
  >
    <span
      aria-hidden="true"
      className="flex items-center justify-center"
      style={{
        width: 34,
        height: 34,
        borderRadius: "var(--r-2)",
        background: "var(--bg-1)",
        border: "1px solid var(--border)",
        color: "var(--fg-2)",
        flexShrink: 0,
      }}
    >
      {icon}
    </span>
    <div
      className="flex flex-col"
      style={{ gap: 2, flex: "1 1 220px", minWidth: 0 }}
    >
      <strong style={{ fontSize: 12.5 }}>{title}</strong>
      <span className="dim" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
        {text}
      </span>
    </div>
    {action}
  </div>
);

// Раздел «Обмен файлом» в настройках проекта: передать проект без сервера,
// выгрузив его в файл, и принять файл от коллеги. Заголовок рисует страница.
export const ExchangeCard = ({ projectId, onNavigate }: ExchangeCardProps) => {
  const { t } = useTranslation("gitExchange");
  const { data: status } = useSyncStatus(projectId);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  // Проект только для чтения принять файл не может: слияние пишет в файлы проекта.
  const readOnly = status?.blocked?.reason === "read_only";

  return (
    <div
      className="flex flex-col"
      style={{ gap: 10 }}
      data-testid="exchange-card"
    >
      <p
        className="dim"
        style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55 }}
      >
        {t("card.lead")}
      </p>
      <ActionRow
        icon={<FileDown size={16} />}
        title={t("card.export.title")}
        text={t("card.export.text")}
        action={
          <button
            type="button"
            className="btn"
            onClick={() => {
              setExportOpen(true);
            }}
          >
            {t("card.export.action")}
          </button>
        }
      />
      <ActionRow
        icon={<FileUp size={16} />}
        title={t("card.import.title")}
        text={t("card.import.text")}
        action={
          <button
            type="button"
            className="btn"
            onClick={() => {
              setImportOpen(true);
            }}
          >
            {t("card.import.action")}
          </button>
        }
      />
      <BundleExportDialog
        isOpen={exportOpen}
        projectId={projectId}
        onClose={() => {
          setExportOpen(false);
        }}
      />
      <BundleImportDialog
        isOpen={importOpen}
        projectId={projectId}
        disabledReason={readOnly ? t("card.import.readOnly") : null}
        {...(onNavigate ? { onNavigate } : {})}
        onClose={() => {
          setImportOpen(false);
        }}
      />
    </div>
  );
};
