import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { Probe } from "@entities/git-remote";
import type { GitContents } from "@entities/git-sync";
import {
  deriveRows,
  rowOfCode,
  type CheckOutcome,
  type CheckRowId,
} from "../model/probeOutcome";
import { ProbeChecklist } from "./ProbeChecklist";
import { ProbeResultCard, type ProbeResultHandlers } from "./ProbeResultCard";
import { StepLayout } from "./StepLayout";

export type CheckStepProps = Omit<ProbeResultHandlers, "onClose"> & {
  /** null: проверка идёт. */
  outcome: CheckOutcome | null;
  probe: Probe | null;
  contents: GitContents | undefined;
  fixing: boolean;
  isConnecting: boolean;
  adoptConfirmed: boolean;
  onAdoptConfirmedChange: (value: boolean) => void;
  onBack: () => void;
  onCancel: () => void;
};

// Шаг 3. Проверка: чек-лист по строкам и карточка с итогом.
export const CheckStep = ({
  outcome,
  probe,
  contents,
  fixing,
  isConnecting,
  adoptConfirmed,
  onAdoptConfirmedChange,
  onBack,
  onCancel,
  ...handlers
}: CheckStepProps) => {
  const { t, i18n } = useTranslation("gitRemote");
  const rows = useMemo(
    () => deriveRows(outcome ? "done" : "running", outcome),
    [outcome],
  );

  const reasons = useMemo((): Partial<Record<CheckRowId, string>> => {
    if (!outcome || outcome.kind === "ready") return {};
    if (outcome.kind === "error") {
      const key = `issue.${outcome.issue.code}.title`;
      return {
        [rowOfCode(outcome.issue.code)]: i18n.exists(`gitRemote:${key}`)
          ? t(key)
          : t("issue.generic.title"),
      };
    }
    const compat: Record<"unrelated" | "other_project" | "not_studio", string> =
      {
        unrelated: t("result.unrelated.title"),
        other_project: t("result.otherProject.title"),
        not_studio: t("result.notStudio.title"),
      };
    return { compatible: compat[outcome.kind] };
  }, [i18n, outcome, t]);

  return (
    <StepLayout
      id="connect-check"
      aria-label={t("connect.steps.check")}
      start={
        <button
          type="button"
          className="btn"
          onClick={onBack}
          disabled={isConnecting}
        >
          {t("connect.back")}
        </button>
      }
      end={
        <button type="button" className="btn" onClick={onCancel}>
          {t("connect.cancel")}
        </button>
      }
    >
      <ProbeChecklist rows={rows} reasons={reasons} />
      {outcome && (
        <ProbeResultCard
          outcome={outcome}
          probe={probe}
          contents={contents}
          fixing={fixing}
          isConnecting={isConnecting}
          adoptConfirmed={adoptConfirmed}
          onAdoptConfirmedChange={onAdoptConfirmedChange}
          onClose={onCancel}
          {...handlers}
        />
      )}
    </StepLayout>
  );
};
