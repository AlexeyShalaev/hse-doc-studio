import { RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Spinner } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import type { ServerSetupCheck } from "@entities/session";
import { REQUIRED_CHECKS, environmentVerdict } from "../lib/steps";
import type { SetupFailure } from "../model/useServerSetup";
import { FailureFrame, PendingLabel, StepActions, StepHeading } from "./parts";

const TONE = {
  ok: "success",
  fail: "error",
  not_configured: "warning",
} as const;

export type EnvironmentStepProps = {
  /** null, пока проверка идёт или не удалась. */
  checks: readonly ServerSetupCheck[] | null;
  loading: boolean;
  /** Сама проверка не выполнилась (сервер не ответил). */
  loadFailed?: boolean;
  completing?: boolean;
  failure?: SetupFailure | null;
  onRecheck: () => void;
  onBack: () => void;
  onComplete: () => void;
};

/** Шаг 5: проверка окружения. Красная обязательная проверка не пускает дальше. */
export const EnvironmentStep = ({
  checks,
  loading,
  loadFailed = false,
  completing = false,
  failure = null,
  onRecheck,
  onBack,
  onComplete,
}: EnvironmentStepProps) => {
  const { t } = useTranslation("auth");
  const verdict = checks ? environmentVerdict(checks) : null;
  const blocked = verdict === null || verdict.blocking.length > 0;

  return (
    <section
      data-testid="setup-step-environment"
      data-blocked={blocked}
      aria-labelledby="setup-title"
    >
      <StepHeading
        id="setup-title"
        title={t("setup.environment.title")}
        lead={t("setup.environment.lead")}
      />
      {failure && <FailureFrame failure={failure} />}

      {loading && checks === null && (
        <div
          className="flex items-center"
          style={{ gap: 10, padding: "14px 0", color: "var(--fg-2)" }}
          role="status"
          data-testid="setup-environment-loading"
        >
          <Spinner size="sm" />
          <span style={{ fontSize: 13 }}>
            {t("setup.environment.checking")}
          </span>
        </div>
      )}

      {loadFailed && !loading && (
        <ResultFrame
          tone="err"
          role="alert"
          testId="setup-environment-failed"
          title={t("setup.environment.loadFailed")}
        >
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
            {t("setup.environment.loadFailedHint")}
          </p>
        </ResultFrame>
      )}

      {checks && (
        <ul
          className="flex flex-col"
          style={{ listStyle: "none", margin: 0, padding: 0, gap: 8 }}
          data-testid="setup-checks"
        >
          {checks.map((check) => {
            const required = REQUIRED_CHECKS.includes(check.id);
            return (
              <li
                key={check.id}
                data-testid={`setup-check-${check.id}`}
                data-status={check.status}
                style={{
                  padding: "10px 14px",
                  borderRadius: "var(--r-3)",
                  border: "1px solid var(--border)",
                  background: "var(--bg-1)",
                }}
              >
                <div className="flex items-center" style={{ gap: 8 }}>
                  <span style={{ flex: 1, fontSize: 13.5, fontWeight: 500 }}>
                    {t(`setup.environment.check.${check.id}`)}
                  </span>
                  {required && (
                    <span className="chip subtle">
                      {t("setup.environment.required")}
                    </span>
                  )}
                  <Badge variant={TONE[check.status]}>
                    {t(`setup.environment.status.${check.status}`)}
                  </Badge>
                </div>
                <p
                  style={{
                    margin: "4px 0 0",
                    fontSize: 12.5,
                    color: "var(--fg-2)",
                  }}
                >
                  {t(`setup.environment.note.${check.id}.${check.status}`)}
                </p>
                {check.status === "fail" && check.reason !== null && (
                  <p
                    className="mono"
                    style={{
                      margin: "4px 0 0",
                      fontSize: 11.5,
                      color: "var(--c-err)",
                    }}
                  >
                    {check.reason}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {verdict && verdict.blocking.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <ResultFrame
            tone="err"
            role="alert"
            testId="setup-environment-blocked"
            title={t("setup.environment.blocked")}
          >
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
              {t("setup.environment.blockedHint")}
            </p>
          </ResultFrame>
        </div>
      )}
      {verdict !== null && !blocked && verdict.warnings.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <ResultFrame
            tone="warn"
            role="status"
            testId="setup-environment-warnings"
            title={t("setup.environment.warnings")}
          >
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
              {t("setup.environment.warningsHint")}
            </p>
          </ResultFrame>
        </div>
      )}

      <div style={{ marginTop: 14 }}>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          aria-disabled={loading}
          style={{ gap: 6 }}
          onClick={() => {
            if (!loading) onRecheck();
          }}
          data-testid="setup-recheck"
        >
          <RotateCw size={13} aria-hidden />
          {t("setup.environment.recheck")}
        </Button>
      </div>

      <StepActions
        onBack={onBack}
        primary={
          <Button
            type="button"
            aria-disabled={blocked || completing}
            style={{ gap: 8 }}
            onClick={() => {
              if (!blocked && !completing) onComplete();
            }}
            data-testid="setup-complete"
          >
            <PendingLabel
              pending={completing}
              idle={t("setup.environment.complete")}
              busy={t("setup.saving")}
            />
          </Button>
        }
      />
    </section>
  );
};
