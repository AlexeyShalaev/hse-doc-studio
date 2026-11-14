import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { localeTag, toast, type ListRequestParams } from "@shared/lib";
import { Button, ErrorState, Modal, Notice, Spinner } from "@shared/ui";
import { resendBatchBodyOf, useResendMailBatch } from "../api/mailLogQueries";
import type { MailLogResendBatch } from "../api/schemas";
import { useBlockedText } from "./labels";

export type ResendBatchState = "counting" | "ready" | "failed";

export type ResendBatchViewProps = {
  state: ResendBatchState;
  /** Предпросмотр сервера: сколько уйдёт и сколько пропущено по причинам. */
  preview: MailLogResendBatch | null;
  /** В адресе стоят фильтры списка: отправка учитывает их. */
  filtered: boolean;
  onRetry: () => void;
};

/**
 * Содержимое окна «Отправить неушедшие» (docs/design/mail-log.md, 14.3, V11): сколько писем
 * уйдёт и сколько пропущено по каждой причине. Окно и кнопки рисует ResendBatchDialog, галерея
 * показывает содержимое отдельно.
 */
export const ResendBatchView = ({
  state,
  preview,
  filtered,
  onRetry,
}: ResendBatchViewProps) => {
  const { t } = useTranslation("adminMail");
  const blockedText = useBlockedText();
  const n = (value: number) => value.toLocaleString(localeTag());
  if (state === "counting") {
    return (
      <div className="ml-batch-state" data-testid="mail-batch-counting">
        <Spinner size="sm" />
        <span>{t("batch.counting")}</span>
      </div>
    );
  }
  if (state === "failed" || preview === null) {
    return (
      <ErrorState
        compact
        title={t("batch.failed")}
        onRetry={onRetry}
        testId="mail-batch-failed"
      />
    );
  }
  const skipped = Object.entries(preview.skipped).sort((a, b) => b[1] - a[1]);
  return (
    <div className="ml-batch" data-testid="mail-batch">
      <p className="ml-batch-lead">{t("batch.lead")}</p>
      {filtered && (
        <div data-testid="mail-batch-filtered">
          <Notice tone="info" text={t("batch.filtered")} />
        </div>
      )}
      <p className="ml-batch-planned" data-testid="mail-batch-planned">
        {preview.planned > 0
          ? t("batch.planned", { n: n(preview.planned) })
          : t("batch.nothing")}
      </p>
      {skipped.length > 0 && (
        <div className="ml-batch-skipped" data-testid="mail-batch-skipped">
          <span className="ml-card-caption">{t("batch.skippedTitle")}</span>
          <ul>
            {skipped.map(([code, count]) => (
              <li key={code} data-code={code}>
                {t("batch.skipped", {
                  reason: blockedText(code, preview.limit),
                  n: n(count),
                })}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export type ResendBatchDialogProps = {
  open: boolean;
  onClose: () => void;
  /** Параметры списка из адреса (state.params): фильтры отправки. */
  params: ListRequestParams;
  filtered: boolean;
};

/** Окно «Отправить неушедшие»: при открытии предпросмотр, по кнопке отправка фоном. */
export const ResendBatchDialog = ({
  open,
  onClose,
  params,
  filtered,
}: ResendBatchDialogProps) => {
  const { t } = useTranslation("adminMail");
  const preview = useResendMailBatch();
  const run = useResendMailBatch();
  // Фильтры как строка: новый объект параметров с теми же условиями не пересчитывает окно.
  const paramsKey = JSON.stringify(params);

  const count = preview.mutate;
  useEffect(() => {
    if (open) {
      count(
        resendBatchBodyOf(JSON.parse(paramsKey) as ListRequestParams, true),
      );
    }
  }, [open, paramsKey, count]);

  const result = preview.data ?? null;
  const state: ResendBatchState = preview.isError
    ? "failed"
    : preview.isPending || result === null
      ? "counting"
      : "ready";
  const planned = result?.planned ?? 0;

  const submit = () => {
    run.mutate(resendBatchBodyOf(params, false), {
      onSuccess: (done) => {
        if (done.started) toast.success(t("batch.started"));
        onClose();
      },
      onError: () => {
        toast.error(t("resend.failed"));
      },
    });
  };

  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      title={t("batch.title")}
      width={520}
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            {t("batch.cancel")}
          </Button>
          <Button
            variant="primary"
            type="button"
            disabled={state !== "ready" || planned === 0 || run.isPending}
            onClick={submit}
            data-testid="mail-batch-submit"
          >
            {run.isPending && <Spinner size="sm" />}
            {t("batch.submit", { n: planned.toLocaleString(localeTag()) })}
          </Button>
        </>
      }
    >
      <ResendBatchView
        state={state}
        preview={result}
        filtered={filtered}
        onRetry={() => {
          count(resendBatchBodyOf(params, true));
        }}
      />
    </Modal>
  );
};
