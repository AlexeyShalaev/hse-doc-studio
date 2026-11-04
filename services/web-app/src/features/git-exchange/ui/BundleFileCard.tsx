import { FileArchive, Lock, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatFileSize } from "@shared/lib";
import { isEncryptedBundleName } from "../lib/bundleNames";

export type BundleFileCardProps = {
  file: File;
  /** Можно заменить или убрать файл (нельзя, пока он загружается). */
  editable: boolean;
  onReplace: () => void;
  onRemove: () => void;
};

// Выбранный файл: значок, имя, размер и пометка «защищён паролем».
export const BundleFileCard = ({
  file,
  editable,
  onReplace,
  onRemove,
}: BundleFileCardProps) => {
  const { t } = useTranslation("gitExchange");
  const encrypted = isEncryptedBundleName(file.name);
  return (
    <div
      className="card flex items-center"
      style={{ gap: "0.75rem", padding: "0.625rem 0.75rem" }}
      data-testid="import-file"
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
        {encrypted ? (
          <Lock size="1rem" aria-hidden="true" />
        ) : (
          <FileArchive size="1rem" aria-hidden="true" />
        )}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          className="mono truncate"
          style={{
            display: "block",
            fontSize: "0.78125rem",
            color: "var(--fg-0)",
          }}
          title={file.name}
        >
          {file.name}
        </span>
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
          {formatFileSize(file.size)}
          {encrypted && ` · ${t("import.encrypted")}`}
        </span>
      </span>
      {editable && (
        <>
          <button type="button" className="btn xs" onClick={onReplace}>
            {t("import.replace")}
          </button>
          <button
            type="button"
            className="btn xs ghost"
            aria-label={t("import.remove")}
            title={t("import.remove")}
            onClick={onRemove}
          >
            <X size="0.8125rem" aria-hidden="true" />
          </button>
        </>
      )}
    </div>
  );
};
