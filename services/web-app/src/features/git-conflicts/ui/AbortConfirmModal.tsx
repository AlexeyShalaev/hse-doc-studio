import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";
import { Modal } from "@shared/ui/Modal";
import { Spinner } from "@shared/ui/Spinner";

export type AbortConfirmModalProps = {
  isOpen: boolean;
  isPending: boolean;
  /** Название последней версии, в которой сохранены мои правки. */
  versionName: string | null;
  onClose: () => void;
  onConfirm: () => void;
};

/** Подтверждение отмены слияния: проект вернётся как был, ничего не теряется. */
export const AbortConfirmModal = ({
  isOpen,
  isPending,
  versionName,
  onClose,
  onConfirm,
}: AbortConfirmModalProps) => {
  const { t } = useTranslation("gitConflicts");
  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!isPending) onClose();
      }}
      title={t("abort.title")}
      width={460}
      footer={
        <div className="flex items-center justify-end" style={{ gap: 8 }}>
          <button
            type="button"
            className="btn"
            onClick={onClose}
            disabled={isPending}
          >
            {t("abort.keep")}
          </button>
          <button
            type="button"
            className="btn danger"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending && <Spinner size="sm" />}
            {t("abort.confirm")}
          </button>
        </div>
      }
    >
      <div
        className="flex items-start"
        style={{
          gap: 8,
          padding: 12,
          borderRadius: "var(--r-2)",
          background: "var(--accent-soft)",
        }}
      >
        <ShieldCheck
          size={15}
          aria-hidden="true"
          style={{ color: "var(--accent)", flexShrink: 0, marginTop: 1 }}
        />
        <span style={{ fontSize: 12, lineHeight: 1.55, color: "var(--fg-1)" }}>
          {versionName
            ? t("abort.text", { name: versionName })
            : t("abort.textPlain")}
        </span>
      </div>
    </Modal>
  );
};
