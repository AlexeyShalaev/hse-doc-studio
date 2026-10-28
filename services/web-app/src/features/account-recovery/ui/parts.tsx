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
  <h1 id={id} style={{ fontSize: 20, fontWeight: 600, margin: "0 0 6px" }}>
    {children}
  </h1>
);

export const Lead = ({ children }: { children: ReactNode }) => (
  <p style={{ margin: "0 0 18px", color: "var(--fg-2)", fontSize: 13.5 }}>
    {children}
  </p>
);

export const Note = ({ children }: { children: ReactNode }) => (
  <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>{children}</p>
);

export const BackToLogin = ({ primary = false }: { primary?: boolean }) => {
  const { t } = useTranslation("auth");
  return (
    <div style={{ marginTop: 18 }}>
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
    <div style={{ marginBottom: 16 }}>
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
