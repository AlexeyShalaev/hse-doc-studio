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
      style={{ gap: 12, padding: "10px 12px" }}
      data-testid="project-import-file"
    >
      <span
        className="flex items-center justify-center"
        style={{
          width: 34,
          height: 34,
          borderRadius: "var(--r-2)",
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
          color: "var(--fg-2)",
          flexShrink: 0,
        }}
      >
        <FileArchive size={16} aria-hidden="true" />
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          className="mono truncate"
          style={{ display: "block", fontSize: 12.5, color: "var(--fg-0)" }}
          title={name}
        >
          {name}
        </span>
        <span className="dim" style={{ fontSize: 11.5 }}>
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
            <X size={13} aria-hidden="true" />
          </button>
        </>
      )}
    </div>
  );
};
