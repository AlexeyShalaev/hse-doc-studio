import { useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Button, Modal, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { SIGNING_TEXT_MAX } from "@entities/signing-route";

export type ReturnDialogProps = {
  open: boolean;
  busy: boolean;
  /** Код отказа сервера: текст из `failure.*`. */
  error?: string | null;
  projectId: string;
  onClose: () => void;
  onSubmit: (comment: string) => void;
};

/**
 * «Вернуть на доработку»: комментарий обязателен, до 2000 символов (раздел 5.6).
 * Подробные замечания к тексту оставляют в проекте обычными комментариями.
 */
export const ReturnDialog = ({
  open,
  busy,
  error = null,
  projectId,
  onClose,
  onSubmit,
}: ReturnDialogProps) => {
  const { t } = useTranslation("signing");
  const [comment, setComment] = useState("");
  const ready = comment.trim().length > 0;
  const submit = () => {
    if (ready && !busy) onSubmit(comment.trim());
  };
  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      title={t("return.title")}
      description={t("return.lead")}
      width={480}
      footer={
        <>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={busy}
          >
            {t("cancel")}
          </Button>
          <Button
            type="submit"
            form="signing-return-form"
            disabled={!ready || busy}
            data-testid="signing-return-submit"
          >
            {busy ? t("actions.working") : t("return.submit")}
          </Button>
        </>
      }
    >
      <form
        id="signing-return-form"
        className="flex flex-col"
        style={{ gap: "0.5rem" }}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Textarea
          id="signing-return-comment"
          label={t("return.label")}
          placeholder={t("return.placeholder")}
          value={comment}
          maxLength={SIGNING_TEXT_MAX}
          rows={4}
          required
          autoFocus
          data-testid="signing-return-comment"
          hint={t("return.counter", {
            n: comment.length,
            max: SIGNING_TEXT_MAX,
          })}
          onChange={(e) => {
            setComment(e.target.value);
          }}
        />
        {error && (
          <Notice tone="err" role="alert" text={t(`failure.${error}`)} />
        )}
        <p className="sgn-hint">
          {t("return.notes")}{" "}
          <Link to={`/projects/${encodeURIComponent(projectId)}`}>
            {t("head.openProject")}
          </Link>
        </p>
      </form>
    </Modal>
  );
};
