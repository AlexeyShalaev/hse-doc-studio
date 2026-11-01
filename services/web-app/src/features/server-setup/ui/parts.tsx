import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Spinner } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import type { SetupFailure } from "../model/useServerSetup";
import { setupErrorKey } from "../lib/setupErrors";

const titleStyle: CSSProperties = {
  fontSize: 20,
  fontWeight: 600,
  margin: "0 0 6px",
};
const leadStyle: CSSProperties = {
  margin: "0 0 18px",
  color: "var(--fg-2)",
  fontSize: 13.5,
};

/** Заголовок шага: у каждого шага один h1, на него ссылается aria-labelledby. */
export const StepHeading = ({
  id,
  title,
  lead,
}: {
  id: string;
  title: string;
  lead: string;
}) => (
  <>
    <h1 id={id} style={titleStyle}>
      {title}
    </h1>
    <p style={leadStyle}>{lead}</p>
  </>
);

/** Метка «задано окружением»: поле показано только для чтения. */
export const LockedBadge = () => {
  const { t } = useTranslation("auth");
  return (
    <Badge variant="info" data-testid="locked-by-env">
      {t("setup.locked")}
    </Badge>
  );
};

/** Отказ шага рамкой над формой; текст по коду, без деталей сервера. */
export const FailureFrame = ({
  failure,
  testId = "setup-error",
}: {
  failure: SetupFailure;
  testId?: string;
}) => {
  const { t } = useTranslation("auth");
  const key = setupErrorKey(failure.code);
  return (
    <div style={{ marginBottom: 16 }}>
      <ResultFrame
        tone={failure.code === "rate_limited" ? "warn" : "err"}
        role="alert"
        testId={testId}
        title={t(key)}
      >
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
          {t(`${key}Hint`, { defaultValue: "" })}
        </p>
      </ResultFrame>
    </div>
  );
};

/** Кнопки шага: «Назад» слева, главное действие справа. */
export const StepActions = ({
  onBack,
  primary,
}: {
  onBack?: (() => void) | undefined;
  primary: ReactNode;
}) => {
  const { t } = useTranslation("auth");
  return (
    <div
      className="flex items-center justify-between"
      style={{ gap: 12, marginTop: 22 }}
    >
      {onBack ? (
        <Button type="button" variant="ghost" onClick={onBack}>
          {t("setup.back")}
        </Button>
      ) : (
        <span />
      )}
      {primary}
    </div>
  );
};

export const PendingLabel = ({
  pending,
  idle,
  busy,
}: {
  pending: boolean;
  idle: string;
  busy: string;
}) => (
  <>
    {pending && <Spinner size="sm" />}
    {pending ? busy : idle}
  </>
);
