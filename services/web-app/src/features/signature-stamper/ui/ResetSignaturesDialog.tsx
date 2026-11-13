import { useTranslation } from "react-i18next";
import { Modal, Spinner } from "@shared/ui";

export type ResetSignaturesDialogProps = {
  isOpen: boolean;
  /** Чьи подписи сбросятся: имена подписантов. */
  names: readonly string[];
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/**
 * Сохранение меток даты на документе под маршрутом, над зафиксированным PDF которого уже есть ЭП
 * (docs/design/signing-route.md, 14.6, 14.11): документ зафиксируют заново, и эти подписи
 * сбросятся. Сервер ответил 409 `resets_signatures`; «Сохранить» повторяет запрос с
 * `confirm_reset`.
 */
export const ResetSignaturesDialog = ({
  isOpen,
  names,
  pending,
  onConfirm,
  onCancel,
}: ResetSignaturesDialogProps) => {
  const { t } = useTranslation("signatureStamper");
  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!pending) onCancel();
      }}
      title={t("dates.confirm.title")}
      footer={
        <>
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={onCancel}
          >
            {t("dates.confirm.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={pending}
            data-testid="dates-reset-confirm"
            onClick={onConfirm}
          >
            {pending && <Spinner size="sm" />}
            {t("dates.confirm.save")}
          </button>
        </>
      }
    >
      <p
        style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}
        data-testid="dates-reset-text"
      >
        {t("dates.confirm.text", { names: names.join(", ") })}
      </p>
    </Modal>
  );
};
