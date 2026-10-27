import { useTranslation } from "react-i18next";
import { CheckCircle2, History, OctagonAlert } from "lucide-react";
import { gitErrorMessage } from "@entities/git-sync";
import { Spinner } from "@shared/ui/Spinner";
import { Stepper, type StepperStep } from "@shared/ui/Stepper";
import type { ConflictCompletion } from "../model/useConflictWorkspace";

export type ApplyProgressProps = {
  completion: Exclude<ConflictCompletion, { kind: "idle" }>;
  isCancelling: boolean;
  onCancel: () => void;
  onRetry: () => void;
  onBack: () => void;
  onOpenHistory: () => void;
};

const STEPS = ["merge", "push"] as const;

const Frame = ({ children }: { children: React.ReactNode }) => (
  <div
    className="card flex flex-col items-center"
    style={{
      gap: 14,
      padding: "32px 28px",
      margin: "0 auto",
      maxWidth: 520,
      width: "100%",
      textAlign: "center",
    }}
  >
    {children}
  </div>
);

/**
 * Что происходит после «Завершить и отправить»: слияние и отправка идут на
 * сервере, поэтому экран можно спокойно оставить. Здесь же итог неудачи.
 */
export const ApplyProgress = ({
  completion,
  isCancelling,
  onCancel,
  onRetry,
  onBack,
  onOpenHistory,
}: ApplyProgressProps) => {
  const { t } = useTranslation("gitConflicts");

  if (completion.kind === "done") {
    return (
      <Frame>
        <CheckCircle2 size={32} style={{ color: "var(--c-ok)" }} aria-hidden />
        <div role="status">
          <h3 style={{ margin: 0, fontSize: 15 }}>{t("apply.doneTitle")}</h3>
          <p className="dim" style={{ margin: "6px 0 0", fontSize: 12.5 }}>
            {t("apply.doneText")}
          </p>
        </div>
      </Frame>
    );
  }

  if (completion.kind === "failed" || completion.kind === "cancelled") {
    const error =
      completion.kind === "failed" ? completion.operation.error : null;
    // Слияние уже закоммичено, не вышла только отправка: конфликтов больше
    // нет, повторять завершение нечем, остаётся история и новая синхронизация.
    const pushFailed =
      completion.kind === "failed" && completion.operation.phase === "push";
    return (
      <Frame>
        <OctagonAlert
          size={32}
          style={{
            color:
              completion.kind === "failed" ? "var(--c-err)" : "var(--fg-2)",
          }}
          aria-hidden
        />
        <div role="alert">
          <h3 style={{ margin: 0, fontSize: 15 }}>
            {completion.kind === "failed"
              ? t("apply.failedTitle")
              : t("apply.cancelledTitle")}
          </h3>
          <p
            className="dim"
            style={{ margin: "6px 0 0", fontSize: 12.5, lineHeight: 1.5 }}
          >
            {error
              ? gitErrorMessage(error.code, error.detail)
              : completion.kind === "failed"
                ? t("apply.failedText")
                : t("apply.cancelledText")}
          </p>
          {pushFailed && (
            <p
              className="dim"
              style={{ margin: "6px 0 0", fontSize: 12.5, lineHeight: 1.5 }}
            >
              {t("apply.pushFailedHint")}
            </p>
          )}
        </div>
        <div className="flex" style={{ gap: 8 }}>
          {pushFailed ? (
            <button
              type="button"
              className="btn primary"
              onClick={onOpenHistory}
            >
              <History size={13} aria-hidden="true" />
              {t("apply.openHistory")}
            </button>
          ) : (
            <>
              {completion.kind === "failed" && (
                <button type="button" className="btn primary" onClick={onRetry}>
                  {t("apply.retry")}
                </button>
              )}
              <button type="button" className="btn" onClick={onBack}>
                {t("apply.back")}
              </button>
            </>
          )}
        </div>
      </Frame>
    );
  }

  const operation = completion.operation;
  const current = operation?.phase === "push" ? "push" : "merge";
  const steps: StepperStep[] = STEPS.map((id) => ({
    id,
    label: t(`apply.phase.${id}`),
    ...(id === current && id === "push" && operation?.percent != null
      ? { meta: `${String(Math.round(operation.percent))}%` }
      : {}),
  }));

  return (
    <Frame>
      <Spinner />
      <div role="status">
        <h3 style={{ margin: 0, fontSize: 15 }}>{t("apply.title")}</h3>
        <p
          className="dim"
          style={{ margin: "6px 0 0", fontSize: 12.5, lineHeight: 1.5 }}
        >
          {t("apply.text")}
        </p>
      </div>
      <div style={{ alignSelf: "stretch", textAlign: "left" }}>
        <Stepper
          steps={steps}
          current={current}
          busy
          orientation="vertical"
          label={t("apply.phases")}
        />
      </div>
      {operation?.cancellable && (
        <button
          type="button"
          className="btn sm"
          disabled={isCancelling}
          onClick={onCancel}
        >
          {t("apply.cancel")}
        </button>
      )}
    </Frame>
  );
};
