import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  CircleHelp,
  FileWarning,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ScenarioBadge } from "../../lib/scenarios";

const ICONS = {
  passed: CheckCircle2,
  failed: CircleAlert,
  error: AlertTriangle,
  unchecked: CircleDashed,
  broken: FileWarning,
  pending: RefreshCw,
  unknown: CircleHelp,
} satisfies Record<ScenarioBadge, typeof CircleAlert>;

type ScenarioStatusProps = {
  status: ScenarioBadge;
  /** Только значок: подпись остаётся для скринридера и подсказки. */
  iconOnly?: boolean;
};

/** Статус прогона сценария: значок и слово (цвет не единственный носитель смысла). */
export const ScenarioStatus = ({ status, iconOnly }: ScenarioStatusProps) => {
  const { t } = useTranslation("packOutcome");
  const Icon = ICONS[status];
  const label = t(`scenarios.status.${status}`);
  return (
    <span
      className="po-sc-status"
      data-status={status}
      title={iconOnly ? label : undefined}
      data-testid={`scenario-status-${status}`}
    >
      <Icon
        size="0.875rem"
        aria-hidden="true"
        className={status === "pending" ? "po-spin" : undefined}
      />
      <span className={iconOnly ? "sr-only" : undefined}>{label}</span>
    </span>
  );
};
