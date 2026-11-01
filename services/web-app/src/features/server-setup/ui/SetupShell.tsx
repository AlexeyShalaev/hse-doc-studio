import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ProgressBar, Stepper, type StepperStep } from "@shared/ui";
import { SETUP_STEPS, type SetupStepId } from "../lib/steps";

export type SetupShellProps = {
  step: SetupStepId;
  /** Идёт запрос шага: на текущем шаге вращается спиннер. */
  busy?: boolean;
  children: ReactNode;
};

/**
 * Каркас мастера: степпер над шагом. На узком экране вместо степпера строка
 * «Шаг N из 6» и полоса хода: шесть подписей в одну строку не помещаются.
 */
export const SetupShell = ({
  step,
  busy = false,
  children,
}: SetupShellProps) => {
  const { t } = useTranslation("auth");
  const index = SETUP_STEPS.indexOf(step);
  const steps: StepperStep[] = SETUP_STEPS.map((id) => ({
    id,
    label: t(`setup.steps.${id}`),
    // Последний шаг не «в работе»: на нём всё уже сделано.
    ...(id === "done" && step === "done" ? { state: "done" as const } : {}),
  }));
  return (
    <div data-testid="setup-wizard" data-step={step}>
      <div className="setup-progress-wide" style={{ marginBottom: 24 }}>
        <Stepper
          steps={steps}
          current={step}
          busy={busy}
          label={t("setup.progress")}
        />
      </div>
      <div className="setup-progress-narrow" style={{ marginBottom: 20 }}>
        <p
          className="mono"
          data-testid="setup-progress-text"
          style={{ margin: "0 0 6px", fontSize: 11.5, color: "var(--fg-2)" }}
        >
          {t("setup.stepOf", {
            n: index + 1,
            total: SETUP_STEPS.length,
            name: t(`setup.steps.${step}`),
          })}
        </p>
        <ProgressBar
          percent={((index + 1) / SETUP_STEPS.length) * 100}
          label={t("setup.progress")}
        />
      </div>
      {children}
    </div>
  );
};
