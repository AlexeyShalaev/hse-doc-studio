import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import { StepHeading } from "./parts";

export type DoneStepProps = {
  /** Что ещё осталось сделать: без почты ссылки выдаются вручную. */
  smtpEnabled: boolean;
  opening?: boolean;
  onOpen: () => void;
};

/** Шаг 6: установка готова, что делать дальше. */
export const DoneStep = ({
  smtpEnabled,
  opening = false,
  onOpen,
}: DoneStepProps) => {
  const { t } = useTranslation("auth");
  const next = [
    "setup.done.next.invite",
    "setup.done.next.sso",
    smtpEnabled ? "setup.done.next.org" : "setup.done.next.smtp",
  ];
  return (
    <section data-testid="setup-step-done" aria-labelledby="setup-title">
      <StepHeading
        id="setup-title"
        title={t("setup.done.title")}
        lead={t("setup.done.lead")}
      />
      <ResultFrame
        tone="ok"
        role="status"
        testId="setup-done"
        title={t("setup.done.ready")}
      >
        <ul
          style={{
            margin: "4px 0 0",
            paddingLeft: 18,
            fontSize: 12.5,
            color: "var(--fg-2)",
            display: "flex",
            flexDirection: "column",
            gap: 3,
          }}
        >
          {next.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ul>
      </ResultFrame>
      <div style={{ marginTop: 22 }}>
        <Button
          type="button"
          aria-disabled={opening}
          style={{ width: "100%", justifyContent: "center", gap: 8 }}
          onClick={() => {
            if (!opening) onOpen();
          }}
          data-testid="setup-open"
        >
          {t("setup.done.open")}
          <ArrowRight size={15} aria-hidden />
        </Button>
      </div>
    </section>
  );
};
