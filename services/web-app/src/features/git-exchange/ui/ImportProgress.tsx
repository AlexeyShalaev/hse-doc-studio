import { useTranslation } from "react-i18next";
import type { GitOperation } from "@entities/git-sync";
import { Stepper, type StepperStep } from "@shared/ui/Stepper";
import { ProgressBar } from "./ProgressBar";

const STEP_IDS = ["snapshot", "verify", "merge"] as const;
type StepId = (typeof STEP_IDS)[number];

// Фазы сервера крупнее наших шагов: сохранение своего, проверка файла, слияние.
const stepOfPhase = (phase: string): StepId => {
  switch (phase) {
    case "verify":
    case "fetch":
    case "download":
      return "verify";
    case "merge":
    case "push":
    case "register":
      return "merge";
    default:
      return "snapshot";
  }
};

export type ImportProgressProps =
  | { kind: "upload"; percent: number | null; operation?: undefined }
  | { kind: "merge"; percent?: undefined; operation: GitOperation | undefined };

// Ход импорта: сначала файл едет на сервер (полоса с процентом), потом
// сервер проверяет его и объединяет с проектом (список шагов).
export const ImportProgress = (props: ImportProgressProps) => {
  const { t } = useTranslation("gitExchange");

  if (props.kind === "upload") {
    const percent = props.percent;
    return (
      <div
        className="flex flex-col"
        style={{ gap: 8 }}
        role="status"
        aria-live="polite"
        data-testid="import-upload"
      >
        <div
          className="flex items-center justify-between"
          style={{ fontSize: 12.5 }}
        >
          <span>{t("import.progress.upload")}</span>
          {percent !== null && (
            <span className="dim mono">{Math.round(percent)}%</span>
          )}
        </div>
        <ProgressBar percent={percent} label={t("import.progress.upload")} />
      </div>
    );
  }

  const operation = props.operation;
  const current = stepOfPhase(operation?.phase ?? "queued");
  const steps: StepperStep[] = STEP_IDS.map((id) => ({
    id,
    label: t(`import.progress.phase.${id}`),
    ...(id === current && operation?.message
      ? { description: operation.message }
      : {}),
  }));
  return (
    <div aria-live="polite" data-testid="import-phases">
      <Stepper
        steps={steps}
        current={current}
        busy
        orientation="vertical"
        label={t("import.progress.label")}
      />
    </div>
  );
};
