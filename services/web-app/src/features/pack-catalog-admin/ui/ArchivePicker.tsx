import { useTranslation } from "react-i18next";
import { ARCHIVE_ACCEPT } from "@entities/pack-catalog";
import { formatFileSize } from "@shared/lib";
import { FileDropZone } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { archiveProblem } from "../lib/archiveProblem";

/** Выбор архива паков: рамка «перетащите или выберите», выбранный файл и предел размера. */
export const ArchivePicker = ({
  file,
  onFile,
  maxBytes,
  disabled = false,
}: {
  file: File | null;
  onFile: (file: File) => void;
  maxBytes: number;
  disabled?: boolean;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  const problem = file ? archiveProblem(file, maxBytes) : null;
  return (
    <div className="flex flex-col" style={{ gap: "0.375rem" }}>
      <FileDropZone
        accept={ARCHIVE_ACCEPT}
        onFile={onFile}
        title={t("add.fileDrop")}
        action={t("add.fileAction")}
        activeTitle={t("add.fileActive")}
        hint={t("add.fileLimit", { size: formatFileSize(maxBytes) })}
        inputLabel={t("add.file")}
        disabled={disabled}
        testId="pc-archive-zone"
        inputTestId="pc-archive-input"
      />
      {file && (
        <span
          className="mono"
          style={{ fontSize: "0.75rem" }}
          data-testid="pc-archive-file"
        >
          {t("add.fileChosen", {
            name: file.name,
            size: formatFileSize(file.size),
          })}
        </span>
      )}
      {problem && <Notice tone="err" role="alert" text={problem} />}
    </div>
  );
};
