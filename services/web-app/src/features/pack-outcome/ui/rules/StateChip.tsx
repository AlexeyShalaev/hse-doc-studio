import { Check, CircleDashed, CircleMinus, CircleX, Minus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui";

/** Состояние элемента словами и значком: цвет не единственный носитель смысла. */
export const ElementState = ({
  state,
  testId,
}: {
  state: string;
  testId?: string;
}) => {
  const { t } = useTranslation("packOutcome");
  const text = t(`rules.state.${state}`, { defaultValue: state });
  const on = state === "active" || state === "present";
  const off = state === "inactive";
  const Icon = on ? Check : off ? CircleMinus : CircleDashed;
  return (
    <Badge
      variant={on ? "success" : off ? "warning" : "subtle"}
      data-testid={testId}
      data-state={state}
    >
      <Icon size="0.75rem" aria-hidden="true" />
      {text}
    </Badge>
  );
};

type Status = "held" | "not_held" | "skipped";

/** Исход решения: выполнено, не выполнено, не проверялось. */
export const DecisionStatus = ({
  status,
  testId,
}: {
  status: Status;
  testId?: string;
}) => {
  const { t } = useTranslation("packOutcome");
  const Icon =
    status === "held" ? Check : status === "not_held" ? CircleX : Minus;
  return (
    <Badge
      variant={
        status === "held"
          ? "success"
          : status === "not_held"
            ? "error"
            : "subtle"
      }
      data-testid={testId}
      data-status={status}
    >
      <Icon size="0.75rem" aria-hidden="true" />
      {t(`rules.status.${status}`)}
    </Badge>
  );
};
