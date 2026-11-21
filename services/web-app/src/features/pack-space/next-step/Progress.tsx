import { Check, CircleAlert, ExternalLink, Loader } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  PackErrorText,
  forkRequired,
  lintFailure,
} from "@entities/pack-studio";
import { Button } from "@shared/ui";
import { isNumberMessage } from "../changes/deriveChangesStatus";
import { isNumberError } from "./numberFix";
import { isPushDenied, takenSuggestion } from "./submitErrors";
import type { SubmitStep } from "./submitSteps";
import type { SubmitController } from "./useSubmit";

const stepText = (
  t: TFunction<"packSpace">,
  step: SubmitStep,
  c: SubmitController,
): string =>
  step === "send" && c.update
    ? t("changes.submit.steps.send_update")
    : t(`changes.submit.steps.${step}`, {
        version:
          step === "number" ? (c.numberFix?.to ?? "") : c.version.version,
      });

/**
 * Ход отправки (pack-studio-ux.md, 5.6): шаги по порядку, что уже сделано, на каком месте
 * остановились и что с этим делать. Показывается, пока идёт отправка или если она оборвалась.
 */
export const Progress = ({
  c,
  onAccess,
  onOpenFile,
  onNumber,
}: {
  c: SubmitController;
  onAccess: () => void;
  onOpenFile: (path: string) => void;
  /** Открыть окно «Номер версии». */
  onNumber: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const { plan, done, failure, running, current } = c;
  if (!plan || (!running && !failure)) return null;
  const error = failure?.error;
  const lint = error ? lintFailure(error) : null;
  const taken = error ? takenSuggestion(error) : null;
  // Форк разобран отдельным блоком: его текст не повторяем.
  const needFork = error ? forkRequired(error) !== null : false;
  // Отказ про номер (по коду или по находке): говорим человеческими словами и открываем окно
  // номера; текст сервера остаётся только в «Подробностях».
  const numberFindings =
    lint?.findings.filter((finding) => isNumberMessage(finding.message)) ?? [];
  const badNumber =
    (error ? isNumberError(error) : false) || numberFindings.length > 0;
  const otherFindings =
    lint?.findings.filter((finding) => !isNumberMessage(finding.message)) ?? [];
  return (
    <div className="sp-sb-block" data-testid="sp-sb-progress">
      <ol className="sp-sb-steps">
        {plan.map((step) => {
          const state = done.includes(step)
            ? "done"
            : failure?.step === step
              ? "failed"
              : current === step
                ? "now"
                : "wait";
          return (
            <li
              key={step}
              data-state={state}
              data-testid={`sp-sb-step-${step}`}
            >
              <span className="sp-sb-step-mark" aria-hidden="true">
                {state === "done" ? (
                  <Check size="0.75rem" />
                ) : state === "failed" ? (
                  <CircleAlert size="0.75rem" />
                ) : state === "now" ? (
                  <Loader size="0.75rem" className="sp-sb-spin" />
                ) : null}
              </span>
              <span>{stepText(t, step, c)}</span>
            </li>
          );
        })}
      </ol>
      {failure && (
        <div className="sp-sb-failure" role="alert" data-testid="sp-sb-failure">
          <strong>
            {t("changes.submit.failure.stopped", {
              step: stepText(t, failure.step, c),
            })}
          </strong>
          {badNumber && (
            <>
              <span data-testid="sp-sb-number-failure">
                {t("changes.submit.failure.number")}
              </span>
              <Button
                size="xs"
                variant="secondary"
                onClick={onNumber}
                data-testid="sp-sb-fix-number"
              >
                {t("changes.submit.release.number")}
              </Button>
              <details className="sp-sb-tech">
                <summary>{t("changes.submit.failure.details")}</summary>
                <span className="mono">
                  {numberFindings.length > 0
                    ? numberFindings
                        .map((finding) => finding.message)
                        .join("\n")
                    : failure.error instanceof Error
                      ? failure.error.message
                      : ""}
                </span>
              </details>
            </>
          )}
          {!needFork && !lint && !taken && !badNumber && (
            <span>
              <PackErrorText error={failure.error} />
            </span>
          )}
          {lint && otherFindings.length > 0 && (
            <>
              <span>{t("changes.submit.failure.lint")}</span>
              <ul className="sp-sb-findings" data-testid="sp-sb-findings">
                {otherFindings.map((finding, index) => (
                  <li key={`${finding.path}:${String(index)}`}>
                    <button
                      type="button"
                      className="sp-ch-link"
                      onClick={() => {
                        onOpenFile(finding.path);
                      }}
                    >
                      {finding.message}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {taken && (
            <>
              <span>
                {t("changes.submit.failure.taken", {
                  version: c.version.version,
                  suggested: taken,
                })}
              </span>
              <Button
                size="xs"
                variant="secondary"
                disabled={c.moving}
                onClick={() => {
                  c.moveTo(taken);
                }}
                data-testid="sp-sb-move"
              >
                {t("changes.submit.failure.moveTo", { version: taken })}
              </Button>
            </>
          )}
          {isPushDenied(failure.error) && (
            <Button size="xs" variant="secondary" onClick={onAccess}>
              {t("changes.submit.failure.access")}
            </Button>
          )}
          {!needFork && !taken && (
            <span className="sp-ch-muted">
              {t("changes.submit.failure.resume")}
            </span>
          )}
          {c.moveError !== null && c.moveError !== undefined && (
            <span>
              <PackErrorText error={c.moveError} />
            </span>
          )}
        </div>
      )}
    </div>
  );
};

/** Ветка ушла на хостинг, а запрос не создался: что случилось и куда идти дальше. */
export const Outcome = ({
  c,
  onAccess,
}: {
  c: SubmitController;
  onAccess: () => void;
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const { outcome } = c;
  if (!outcome) return null;
  const prError = outcome.pr_error;
  return (
    <div className="sp-sb-block" data-testid="sp-sb-outcome">
      <div className="sp-sb-failure" role="status">
        <strong>{t("changes.submit.outcome.title")}</strong>
        <span>
          {prError
            ? i18n.exists(`errors:code.${prError.code}`)
              ? t(`errors:code.${prError.code}`)
              : prError.detail
            : t("changes.submit.outcome.lead")}
        </span>
        {prError && (
          <Button size="xs" variant="secondary" onClick={onAccess}>
            {t("changes.submit.failure.access")}
          </Button>
        )}
        {outcome.compare_url && (
          <a
            className="btn sm"
            href={outcome.compare_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="sp-sb-compare"
          >
            <ExternalLink size="0.75rem" aria-hidden="true" />
            {t("changes.submit.outcome.open")}
          </a>
        )}
      </div>
    </div>
  );
};
