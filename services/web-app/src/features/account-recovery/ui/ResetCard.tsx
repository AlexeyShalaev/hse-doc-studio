import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, Spinner } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import type { RecoveryFailure } from "../lib/recoveryErrors";
import { BackToLogin, FailureFrame, Heading, Lead, Note } from "./parts";

const errorProp = (error: string | undefined) => (error ? { error } : {});

export type ResetCardProps = {
  minLength: number;
  pending?: boolean;
  failure?: RecoveryFailure | null;
  onSubmit: (password: string) => void;
};

/** Новый пароль по ссылке из письма. */
export const ResetCard = ({
  minLength,
  pending = false,
  failure = null,
  onSubmit,
}: ResetCardProps) => {
  const { t } = useTranslation("auth");
  const uid = useId();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);

  const tooShort = password.length > 0 && password.length < minLength;
  const mismatch = confirm.length > 0 && confirm !== password;
  const valid = password.length >= minLength && confirm === password;
  const policy = failure?.code === "password_policy";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (pending || !valid) return;
    onSubmit(password);
  };

  return (
    <section data-testid="auth-screen-reset" aria-labelledby={`${uid}-title`}>
      <Heading id={`${uid}-title`}>{t("pages.reset.title")}</Heading>
      <Lead>{t("pages.reset.body")}</Lead>
      {failure && !policy && (
        <FailureFrame failure={failure} testId="reset-error" />
      )}
      <form
        onSubmit={submit}
        className="flex flex-col"
        style={{ gap: 14 }}
        data-testid="reset-form"
      >
        <Input
          id={`${uid}-password`}
          label={t("reset.password")}
          type="password"
          name="password"
          autoComplete="new-password"
          autoFocus
          required
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
          }}
          readOnly={pending}
          hint={t("register.passwordHint", { count: minLength })}
          {...errorProp(
            policy
              ? t("recovery.errors.password_policy")
              : touched && tooShort
                ? t("register.passwordShort", { count: minLength })
                : undefined,
          )}
        />
        <Input
          id={`${uid}-confirm`}
          label={t("register.confirm")}
          type="password"
          name="confirm"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => {
            setConfirm(e.target.value);
          }}
          readOnly={pending}
          {...errorProp(mismatch ? t("register.mismatch") : undefined)}
        />
        <Button
          type="submit"
          aria-disabled={pending}
          style={{ justifyContent: "center", gap: 8 }}
        >
          {pending ? (
            <Spinner size="sm" />
          ) : (
            <KeyRound size={15} aria-hidden="true" />
          )}
          {pending ? t("reset.submitting") : t("reset.submit")}
        </Button>
      </form>
    </section>
  );
};

export const ResetDoneCard = () => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="auth-screen-resetDone">
      <Heading>{t("pages.reset.title")}</Heading>
      <div style={{ height: 12 }} />
      <ResultFrame
        tone="ok"
        role="status"
        testId="reset-done"
        title={t("reset.done.title")}
      >
        <Note>{t("reset.done.body")}</Note>
      </ResultFrame>
      <BackToLogin primary />
    </section>
  );
};

/** Ссылка недействительна или просрочена: путь один, запросить новую. */
export const ResetExpiredCard = () => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="auth-screen-resetExpired">
      <Heading>{t("pages.reset.title")}</Heading>
      <div style={{ height: 12 }} />
      <ResultFrame
        tone="warn"
        role="alert"
        testId="reset-expired"
        title={t("reset.expired.title")}
      >
        <Note>{t("reset.expired.body")}</Note>
      </ResultFrame>
      <div style={{ marginTop: 18 }}>
        <Button asChild style={{ width: "100%", justifyContent: "center" }}>
          <Link to="/forgot">{t("reset.expired.action")}</Link>
        </Button>
      </div>
    </section>
  );
};
