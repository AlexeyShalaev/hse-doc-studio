import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Info, UploadCloud } from "lucide-react";
import { classifyCustomFile, useCustomFileActions } from "@entities/document";
import { toast } from "@shared/lib";
import { Modal, Spinner } from "@shared/ui";

export type UploadCustomFileModalProps = {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  docId: string;
  docName: string;
};

export const UploadCustomFileModal = ({
  isOpen,
  onClose,
  projectId,
  docId,
  docName,
}: UploadCustomFileModalProps) => {
  const { t } = useTranslation("documents");
  const { upload, isUploading } = useCustomFileActions(projectId, docId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [selected, setSelected] = useState<File | null>(null);

  const handleClose = () => {
    if (isUploading) return;
    setSelected(null);
    setDragging(false);
    onClose();
  };

  const pickFile = (files: FileList | File[]) => {
    const file = Array.from(files)[0];
    if (file) setSelected(file);
  };

  const handleUpload = () => {
    if (!selected) return;
    upload(selected)
      .then(() => {
        toast.success(t("customFile.uploadedToast", { name: selected.name }));
        setSelected(null);
        onClose();
      })
      .catch(() => {
        // per-request error toast already shown by the axios interceptor
      });
  };

  const cls = selected ? classifyCustomFile(selected.name) : null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={t("customFile.uploadModalTitle")}
      description={t("customFile.uploadModalDescription", { name: docName })}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={handleClose}
            disabled={isUploading}
          >
            {t("customFile.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={handleUpload}
            disabled={!selected || isUploading}
          >
            {isUploading && <Spinner size="sm" />}
            {t("customFile.uploadAction")}
          </button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: 12 }}>
        <input
          ref={fileRef}
          type="file"
          onChange={(e) => {
            if (e.target.files) pickFile(e.target.files);
          }}
          style={{ display: "none" }}
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => {
            setDragging(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pickFile(e.dataTransfer.files);
          }}
          disabled={isUploading}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            padding: "28px 16px",
            borderRadius: 8,
            border: `1.5px dashed ${dragging ? "var(--accent)" : "var(--border)"}`,
            background: dragging ? "var(--bg-3, var(--bg-2))" : "var(--bg-2)",
            color: "var(--fg-1)",
            cursor: "pointer",
            textAlign: "center",
            transition: "border-color 0.15s, background 0.15s",
          }}
        >
          {selected ? (
            <FileText size={26} style={{ color: "var(--accent)" }} />
          ) : (
            <UploadCloud size={26} style={{ color: "var(--accent)" }} />
          )}
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            {selected
              ? selected.name
              : dragging
                ? t("customFile.dropActive")
                : t("customFile.dropTitle")}
          </span>
          <span style={{ fontSize: 11.5, color: "var(--fg-3)" }}>
            {t("customFile.dropHint")}
          </span>
        </button>

        {cls != null && (
          <div
            className="flex items-start gap-2"
            style={{
              padding: "10px 14px",
              borderRadius: 8,
              background:
                cls === "unknown" ? "var(--bg-2)" : "var(--c-info-soft)",
              border: cls === "unknown" ? "1px solid var(--border)" : "none",
              fontSize: 12,
              lineHeight: 1.5,
              color: "var(--fg-1)",
            }}
          >
            <Info
              size={14}
              style={{
                color: cls === "unknown" ? "var(--fg-3)" : "var(--c-info)",
                flexShrink: 0,
                marginTop: 1,
              }}
            />
            <span>
              {t(
                cls === "convertible"
                  ? "customFile.classConvertible"
                  : cls === "pdf"
                    ? "customFile.classPdf"
                    : "customFile.classUnknown",
              )}
            </span>
          </div>
        )}
      </div>
    </Modal>
  );
};
