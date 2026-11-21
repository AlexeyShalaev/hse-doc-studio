import { Check, CircleAlert, ExternalLink, Loader } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  PackErrorText,
  forkRequired,
  lintFailure,
} from "@entities/pack-studio";
import { Button } from "@shared/ui";
import { isPushDenied, takenSuggestion } from "./submitErrors";
import type { SubmitStep } from "./submitSteps";
import type { SubmitController } from "./useSubmit";

const stepText = (
  t: TFunction<"packSpace">,
  step: SubmitStep,
  c: SubmitController,
): string =>
  step === "send" && c.update
    ? t("submit.steps.send_update")
    : t(`submit.steps.${step}`, { version: c.version.version });

/**
 * Ход отправки (pack-studio-ux.md, 5.6): шаги по порядку, что уже сделано, на каком месте
 * остановились и что с этим делать. Показывается, пока идёт отправка или если она оборвалась.
 */
export const Progress = ({
  c,
  onAccess,
  onOpenFile,
}: {
  c: SubmitController;
  onAccess: () => void;
  onOpenFile: (path: string) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const { plan, done, failure, running, current } = c;
  if (!plan || (!running && !failure)) return null;
  const error = failure?.error;
  const lint = error ? lintFailure(error) : null;
  const taken = error ? takenSuggestion(error) : null;
  // Форк разобран отдельным блоком: его текст не повторяем.
  const needFork = error ? forkRequired(error) !== null : false;
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
            {t("submit.failure.stopped", {
              step: stepText(t, failure.step, c),
            })}
          </strong>
          {!needFork && !lint && !taken && (
            <span>
              <PackErrorText error={failure.error} />
            </span>
          )}
          {lint && (
            <>
              <span>{t("submit.failure.lint")}</span>
              <ul className="sp-sb-findings" data-testid="sp-sb-findings">
                {lint.findings.map((finding, index) => (
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
                {t("submit.failure.taken", {
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
                {t("submit.failure.moveTo", { version: taken })}
              </Button>
            </>
          )}
          {isPushDenied(failure.error) && (
            <Button size="xs" variant="secondary" onClick={onAccess}>
              {t("submit.failure.access")}
            </Button>
          )}
          {!needFork && !taken && (
            <span className="sp-ch-muted">{t("submit.failure.resume")}</span>
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
        <strong>{t("submit.outcome.title")}</strong>
        <span>
          {prError
            ? i18n.exists(`errors:code.${prError.code}`)
              ? t(`errors:code.${prError.code}`)
              : prError.detail
            : t("submit.outcome.lead")}
        </span>
        {prError && (
          <Button size="xs" variant="secondary" onClick={onAccess}>
            {t("submit.failure.access")}
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
            {t("submit.outcome.open")}
          </a>
        )}
      </div>
    </div>
  );
};
