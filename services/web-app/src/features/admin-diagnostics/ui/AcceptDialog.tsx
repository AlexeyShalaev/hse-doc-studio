import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Modal, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useAcceptWarning } from "../api/queries";
import { REASON_MAX, untilOfDate } from "../lib/acceptance";

type Term = "forever" | "until";

/**
 * «Принимаю: не делаю сознательно». Причина обязательна (до 200 символов), срок нет:
 * по умолчанию бессрочно. Принятие можно вернуть, об этом сказано в окне.
 */
export const AcceptDialog = ({
  check,
  onClose,
}: {
  check: string;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminDiagnostics");
  const accept = useAcceptWarning();
  const [reason, setReason] = useState("");
  const [term, setTerm] = useState<Term>("forever");
  const [date, setDate] = useState("");
  const until = term === "until" ? untilOfDate(date) : null;
  const valid =
    reason.trim().length > 0 &&
    reason.length <= REASON_MAX &&
    (term === "forever" || until !== null);

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={t("accept.title", {
        check: t(`check.${check}`, { defaultValue: check }),
      })}
      description={t("accept.lead")}
      footer={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            data-testid="diag-accept-cancel"
          >
            {t("accept.cancel")}
          </Button>
          <Button
            type="button"
            disabled={!valid || accept.isPending}
            data-testid="diag-accept-submit"
            onClick={() => {
              accept.mutate(
                { check, body: { reason: reason.trim(), until } },
                { onSuccess: onClose },
              );
            }}
          >
            {t("accept.submit")}
          </Button>
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        data-testid="diag-accept-dialog"
      >
        <Notice tone="info" text={t("accept.consequences")} />
        <Textarea
          id="diag-accept-reason"
          label={t("accept.reason")}
          hint={t("accept.reasonHint", {
            count: reason.length,
            max: REASON_MAX,
          })}
          rows={3}
          maxLength={REASON_MAX}
          value={reason}
          onChange={(e) => {
            setReason(e.target.value);
          }}
          data-testid="diag-accept-reason"
        />
        <fieldset
          className="flex flex-col"
          style={{ gap: "0.375rem", border: 0, padding: 0, margin: 0 }}
        >
          <legend className="form-hint">{t("accept.term")}</legend>
          <label className="flex items-center" style={{ gap: "0.5rem" }}>
            <input
              type="radio"
              name="diag-accept-term"
              checked={term === "forever"}
              onChange={() => {
                setTerm("forever");
              }}
              data-testid="diag-accept-forever"
            />
            {t("accept.forever")}
          </label>
          <label className="flex items-center" style={{ gap: "0.5rem" }}>
            <input
              type="radio"
              name="diag-accept-term"
              checked={term === "until"}
              onChange={() => {
                setTerm("until");
              }}
              data-testid="diag-accept-until"
            />
            {t("accept.until")}
          </label>
          {term === "until" && (
            <Input
              type="date"
              value={date}
              aria-label={t("accept.untilDate")}
              onChange={(e) => {
                setDate(e.target.value);
              }}
              data-testid="diag-accept-date"
            />
          )}
        </fieldset>
        <p className="form-hint" data-testid="diag-accept-revert">
          {t("accept.revertHint")}
        </p>
        {accept.isError && (
          <div data-testid="diag-accept-failed">
            <Notice tone="warn" role="alert" text={t("accept.failed")} />
          </div>
        )}
      </div>
    </Modal>
  );
};
