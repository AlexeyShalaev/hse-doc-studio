import type { ReactNode } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import { recoveryErrorKey, type RecoveryFailure } from "../lib/recoveryErrors";

export const Heading = ({
  id,
  children,
}: {
  id?: string;
  children: string;
}) => (
  <h1
    id={id}
    style={{ fontSize: "1.25rem", fontWeight: 600, margin: "0 0 0.375rem" }}
  >
    {children}
  </h1>
);

export const Lead = ({ children }: { children: ReactNode }) => (
  <p
    style={{
      margin: "0 0 1.125rem",
      color: "var(--fg-2)",
      fontSize: "0.84375rem",
    }}
  >
    {children}
  </p>
);

export const Note = ({ children }: { children: ReactNode }) => (
  <p style={{ margin: 0, fontSize: "0.78125rem", color: "var(--fg-2)" }}>
    {children}
  </p>
);

export const BackToLogin = ({ primary = false }: { primary?: boolean }) => {
  const { t } = useTranslation("auth");
  return (
    <div style={{ marginTop: "1.125rem" }}>
      <Button
        asChild
        variant={primary ? "primary" : "secondary"}
        style={{ width: "100%", justifyContent: "center" }}
      >
        <Link to="/login">{t("links.login")}</Link>
      </Button>
    </div>
  );
};

export const FailureFrame = ({
  failure,
  testId,
}: {
  failure: RecoveryFailure;
  testId: string;
}) => {
  const { t } = useTranslation("auth");
  const key = recoveryErrorKey(failure.code);
  return (
    <div style={{ marginBottom: "1rem" }}>
      <ResultFrame
        tone={failure.code === "rate_limited" ? "warn" : "err"}
        role="alert"
        testId={testId}
        title={t(key)}
      >
        <Note>{t(`${key}Hint`, { defaultValue: "" })}</Note>
      </ResultFrame>
    </div>
  );
};
