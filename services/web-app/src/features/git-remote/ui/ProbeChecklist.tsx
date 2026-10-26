import { useTranslation } from "react-i18next";
import { Stepper, type StepState, type StepperStep } from "@shared/ui/Stepper";
import {
  CHECK_ROWS,
  type CheckRowId,
  type CheckRowState,
} from "../model/probeOutcome";

export type ProbeChecklistProps = {
  rows: Record<CheckRowId, CheckRowState>;
  /** Короткая причина под строкой, которая не прошла. */
  reasons?: Partial<Record<CheckRowId, string>>;
};

const STEP_STATE: Record<CheckRowState, StepState> = {
  pending: "upcoming",
  skipped: "upcoming",
  running: "current",
  ok: "done",
  fail: "error",
};

// Чек-лист проверки: адрес доступен, доступ принят, репозиторий найден, история
// подходит. Область живая: экранный диктор озвучивает каждую строку по мере
// готовности (состояние строки уже есть в скрытом тексте шага).
export const ProbeChecklist = ({ rows, reasons = {} }: ProbeChecklistProps) => {
  const { t } = useTranslation("gitRemote");
  const running = CHECK_ROWS.find((id) => rows[id] === "running");
  const steps: StepperStep[] = CHECK_ROWS.map((id) => {
    const reason = reasons[id];
    return {
      id,
      label: t(`check.${id}`),
      state: STEP_STATE[rows[id]],
      ...(reason ? { description: reason } : {}),
    };
  });
  return (
    <div aria-live="polite" data-testid="probe-checklist">
      <Stepper
        steps={steps}
        current={running ?? "reachable"}
        busy={running !== undefined}
        orientation="vertical"
        label={t("check.label")}
      />
    </div>
  );
};
