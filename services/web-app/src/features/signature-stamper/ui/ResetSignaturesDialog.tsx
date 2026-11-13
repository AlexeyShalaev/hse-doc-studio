import { useTranslation } from "react-i18next";
import { Modal, Spinner } from "@shared/ui";

export type ResetSignaturesDialogProps = {
  isOpen: boolean;
  /** Чьи подписи сбросятся: имена подписантов. */
  names: readonly string[];
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /**
   * Тексты окна в словаре signatureStamper: заголовок, текст с `{{names}}` и кнопка согласия. По
   * умолчанию окно сохранения меток даты (`dates.confirm`).
   */
  texts?: { title: string; text: string; confirm: string };
};

const DATES_TEXTS = {
  title: "dates.confirm.title",
  text: "dates.confirm.text",
  confirm: "dates.confirm.save",
} as const;

/**
 * Сохранение меток даты на документе под маршрутом, над зафиксированным PDF которого уже есть ЭП
 * (docs/design/signing-route.md, 14.6, 14.11): документ зафиксируют заново, и эти подписи
 * сбросятся. Сервер ответил 409 `resets_signatures`; «Сохранить» повторяет запрос с
 * `confirm_reset`. Тем же окном спрашивает «Вернуть место из шаблона» (15.6) со своими текстами.
 */
export const ResetSignaturesDialog = ({
  isOpen,
  names,
  pending,
  onConfirm,
  onCancel,
  texts = DATES_TEXTS,
}: ResetSignaturesDialogProps) => {
  const { t } = useTranslation("signatureStamper");
  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!pending) onCancel();
      }}
      title={t(texts.title)}
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
            {t(texts.confirm)}
          </button>
        </>
      }
    >
      <p
        style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}
        data-testid="dates-reset-text"
      >
        {t(texts.text, {
          // Имя с инициалами кончается точкой («Петров П. П.»): за ним в тексте своя точка.
          names: names.join(", ").replace(/\.$/, ""),
        })}
      </p>
    </Modal>
  );
};
