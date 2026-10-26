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
      style={{ gap: 12, padding: "10px 12px" }}
      data-testid="import-file"
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
        {encrypted ? (
          <Lock size={16} aria-hidden="true" />
        ) : (
          <FileArchive size={16} aria-hidden="true" />
        )}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          className="mono truncate"
          style={{ display: "block", fontSize: 12.5, color: "var(--fg-0)" }}
          title={file.name}
        >
          {file.name}
        </span>
        <span className="dim" style={{ fontSize: 11.5 }}>
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
            <X size={13} aria-hidden="true" />
          </button>
        </>
      )}
    </div>
  );
};
