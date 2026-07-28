import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";
import type { CustomFilePreflightItemDto } from "@shared/api/types";
import { pickLocalized } from "@shared/lib";
import { Modal } from "@shared/ui";

export type CustomFileDecisionsModalProps = {
  isOpen: boolean;
  onClose: () => void;
  items: readonly CustomFilePreflightItemDto[];
  lang: string;
  onConfirm: (decisions: Record<string, boolean>) => void;
  isSubmitting?: boolean;
};

export const CustomFileDecisionsModal = ({
  isOpen,
  onClose,
  items,
  lang,
  onConfirm,
  isSubmitting,
}: CustomFileDecisionsModalProps) => {
  const { t } = useTranslation("workspace");
  const [decisions, setDecisions] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      items
        .filter((it) => it.convertible)
        .map((it) => [it.doc_id, it.default_decision ?? true]),
    ),
  );

  const toggle = (docId: string) => {
    setDecisions((prev) => ({ ...prev, [docId]: !prev[docId] }));
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("customFilesModal.title")}
      description={t("customFilesModal.description")}
      width={560}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={onClose}
            disabled={isSubmitting}
          >
            {t("customFilesModal.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={isSubmitting}
            onClick={() => {
              onConfirm(decisions);
            }}
          >
            {t("customFilesModal.confirm")}
          </button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: 8 }}>
        {items.map((it) => (
          <div
            key={it.doc_id}
            className="flex items-center justify-between gap-3"
            style={{
              padding: 12,
              background: "var(--bg-2)",
              borderRadius: "var(--r-2)",
              border: "1px solid var(--border)",
              flexWrap: "wrap",
            }}
          >
            <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
              <FileText
                size={13}
                style={{ color: "var(--accent)", flexShrink: 0 }}
              />
              <div className="flex flex-col" style={{ gap: 1, minWidth: 0 }}>
                <strong className="truncate" style={{ fontSize: 12.5 }}>
                  {pickLocalized(it.doc_name, lang, it.doc_id)}
                </strong>
                <span
                  className="mono dim truncate"
                  style={{ fontSize: 10.5 }}
                  title={it.original_filename}
                >
                  {it.original_filename}
                </span>
              </div>
            </div>
            {it.convertible ? (
              <label
                className="flex items-center gap-2"
                style={{ fontSize: 11.5, color: "var(--fg-1)" }}
              >
                {t("customFilesModal.convertToPdf")}
                <span
                  role="switch"
                  aria-checked={decisions[it.doc_id] ?? false}
                  tabIndex={0}
                  className={
                    "toggle" + ((decisions[it.doc_id] ?? false) ? " on" : "")
                  }
                  onClick={() => {
                    toggle(it.doc_id);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === " " || e.key === "Enter") {
                      e.preventDefault();
                      toggle(it.doc_id);
                    }
                  }}
                />
              </label>
            ) : (
              <span
                className="dim"
                style={{ fontSize: 11, textAlign: "right", maxWidth: 220 }}
              >
                {t("customFilesModal.unknownFormatNote")}
              </span>
            )}
          </div>
        ))}
      </div>
    </Modal>
  );
};
