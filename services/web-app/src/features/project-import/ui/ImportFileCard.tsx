import { FileArchive, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatFileSize } from "@shared/lib";

export type ImportFileCardProps = {
  name: string;
  size: number;
  /** Файл можно заменить или убрать (нельзя, пока он загружается). */
  editable: boolean;
  onReplace?: () => void;
  onRemove?: () => void;
};

// Выбранный архив: значок, имя и размер.
export const ImportFileCard = ({
  name,
  size,
  editable,
  onReplace,
  onRemove,
}: ImportFileCardProps) => {
  const { t } = useTranslation("projectImport");
  return (
    <div
      className="card flex items-center"
      style={{ gap: "0.75rem", padding: "0.625rem 0.75rem" }}
      data-testid="project-import-file"
    >
      <span
        className="flex items-center justify-center"
        style={{
          width: "2.125rem",
          height: "2.125rem",
          borderRadius: "var(--r-2)",
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
          color: "var(--fg-2)",
          flexShrink: 0,
        }}
      >
        <FileArchive size="1rem" aria-hidden="true" />
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          className="mono truncate"
          style={{
            display: "block",
            fontSize: "0.78125rem",
            color: "var(--fg-0)",
          }}
          title={name}
        >
          {name}
        </span>
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
          {formatFileSize(size)}
        </span>
      </span>
      {editable && (
        <>
          <button type="button" className="btn xs" onClick={onReplace}>
            {t("replace")}
          </button>
          <button
            type="button"
            className="btn xs ghost"
            aria-label={t("remove")}
            title={t("remove")}
            onClick={onRemove}
          >
            <X size="0.8125rem" aria-hidden="true" />
          </button>
        </>
      )}
    </div>
  );
};
