import { useId, useState, type FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, ResultFrame, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS } from "../lib/styles";
import { AccountCard } from "./parts";

export type PasswordCardProps = {
  minLength: number;
  /** Вход только через SSO: пароля у аккаунта нет. */
  passwordEnabled?: boolean;
  pending?: boolean;
  failure?: Failure | null;
  /** Пароль только что сменён. */
  done?: boolean;
  onSubmit: (input: {
    current: string;
    next: string;
    signOutOthers: boolean;
  }) => void;
};

const errorProp = (error: string | undefined) => (error ? { error } : {});

/** Смена пароля: текущий пароль, новый, повтор и выбор «закрыть остальные сессии». */
export const PasswordCard = ({
  minLength,
  passwordEnabled = true,
  pending = false,
  failure = null,
  done = false,
  onSubmit,
}: PasswordCardProps) => {
  const { t } = useTranslation("account");
  const uid = useId();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [signOutOthers, setSignOutOthers] = useState(true);
  const [touched, setTouched] = useState(false);

  if (!passwordEnabled) {
    return (
      <AccountCard
        id="account-password"
        title={t("password.title")}
        testId="account-password"
      >
        <Notice tone="info" text={t("password.ssoOnly")} />
      </AccountCard>
    );
  }

  const tooShort = next.length > 0 && next.length < minLength;
  const mismatch = confirm.length > 0 && confirm !== next;
  const same = next.length > 0 && next === current;
  const valid =
    current.length > 0 && next.length >= minLength && confirm === next && !same;
  const code = failure?.code;
  const fieldFailure =
    code === "invalid_credentials" || code === "password_policy";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (pending || !valid) return;
    onSubmit({ current, next, signOutOthers });
  };

  return (
    <AccountCard
      id="account-password"
      title={t("password.title")}
      sub={t("password.sub")}
      testId="account-password"
    >
      <form
        onSubmit={submit}
        className="flex flex-col"
        style={{ gap: 12, maxWidth: 420 }}
        data-testid="password-form"
      >
        <Input
          id={`${uid}-current`}
          label={t("password.current")}
          type="password"
          name="current-password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => {
            setCurrent(e.target.value);
          }}
          readOnly={pending}
          {...errorProp(
            code === "invalid_credentials"
              ? t("failure.invalid_credentials")
              : undefined,
          )}
        />
        <Input
          id={`${uid}-new`}
          label={t("password.next")}
          type="password"
          name="new-password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => {
            setNext(e.target.value);
          }}
          readOnly={pending}
          hint={t("password.hint", { count: minLength })}
          {...errorProp(
            code === "password_policy"
              ? t("failure.password_policy")
              : touched && tooShort
                ? t("password.short", { count: minLength })
                : touched && same
                  ? t("password.same")
                  : undefined,
          )}
        />
        <Input
          id={`${uid}-confirm`}
          label={t("password.confirm")}
          type="password"
          name="confirm-password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => {
            setConfirm(e.target.value);
          }}
          readOnly={pending}
          {...errorProp(mismatch ? t("password.mismatch") : undefined)}
        />
        <label
          className="flex"
          style={{ gap: 10, alignItems: "flex-start", fontSize: 12.5 }}
        >
          <input
            type="checkbox"
            checked={signOutOthers}
            onChange={(e) => {
              setSignOutOthers(e.target.checked);
            }}
            style={{ marginTop: 3 }}
          />
          <span className="flex flex-col" style={{ gap: 2 }}>
            <span>{t("password.signOutOthers")}</span>
            <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
              {t("password.signOutOthersHint")}
            </span>
          </span>
        </label>

        {failure && !fieldFailure && (
          <Notice
            tone={code === "rate_limited" ? "warn" : "err"}
            role="alert"
            text={t(failureKey(failure.code))}
          />
        )}
        {done && !failure && (
          <ResultFrame
            tone="ok"
            role="status"
            testId="password-done"
            title={t("password.done")}
          />
        )}

        <div style={ACTIONS}>
          <Button
            type="submit"
            aria-disabled={pending}
            style={{ gap: 8 }}
            data-testid="password-submit"
          >
            {pending ? (
              <Spinner size="sm" />
            ) : (
              <KeyRound size={14} aria-hidden="true" />
            )}
            {pending ? t("password.submitting") : t("password.submit")}
          </Button>
        </div>
      </form>
    </AccountCard>
  );
};
