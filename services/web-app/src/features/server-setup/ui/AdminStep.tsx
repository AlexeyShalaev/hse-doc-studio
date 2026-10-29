import { useId, useState, type FormEvent } from "react";
import { UserCog } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import { fieldOfSetupFailure, setupErrorKey } from "../lib/setupErrors";
import type { SetupFailure } from "../model/useServerSetup";
import { FailureFrame, PendingLabel, StepActions, StepHeading } from "./parts";

// exactOptionalPropertyTypes: пустое значение не передаётся вовсе.
const errorProp = (error: string | undefined) => (error ? { error } : {});

export type AdminStepProps = {
  /** Токен установки нужен, пока администратора нет и он не пришёл из окружения. */
  tokenRequired: boolean;
  passwordMin: number;
  pending?: boolean;
  failure?: SetupFailure | null;
  /** Администратор уже создан: шаг только читается. */
  created?: { name: string; email: string } | null;
  initial?: { name?: string; email?: string; token?: string };
  onSubmit: (input: {
    setup_token: string | null;
    name: string;
    email: string;
    password: string;
  }) => void;
  onBack: () => void;
  onNext: () => void;
};

/** Шаг 2: первый администратор установки. */
export const AdminStep = ({
  tokenRequired,
  passwordMin,
  pending = false,
  failure = null,
  created = null,
  initial = {},
  onSubmit,
  onBack,
  onNext,
}: AdminStepProps) => {
  const { t } = useTranslation("auth");
  const uid = useId();
  const [token, setToken] = useState(initial.token ?? "");
  const [name, setName] = useState(initial.name ?? "");
  const [email, setEmail] = useState(initial.email ?? "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);

  if (created) {
    return (
      <section
        data-testid="setup-step-admin"
        data-readonly="true"
        aria-labelledby="setup-title"
      >
        <StepHeading
          id="setup-title"
          title={t("setup.admin.title")}
          lead={t("setup.admin.createdLead")}
        />
        <ResultFrame
          tone="ok"
          role="status"
          testId="setup-admin-created"
          title={t("setup.admin.created")}
        >
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
            {created.name}
            {" · "}
            <span className="mono">{created.email}</span>
          </p>
        </ResultFrame>
        <StepActions
          onBack={onBack}
          primary={
            <Button type="button" onClick={onNext} data-testid="setup-next">
              {t("setup.next")}
            </Button>
          }
        />
      </section>
    );
  }

  const tooShort = password.length > 0 && password.length < passwordMin;
  const mismatch = confirm.length > 0 && confirm !== password;
  const valid =
    (!tokenRequired || token.trim() !== "") &&
    name.trim() !== "" &&
    email.trim() !== "" &&
    password.length >= passwordMin &&
    confirm === password;
  const field = failure ? fieldOfSetupFailure(failure.code) : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (pending || !valid) return;
    onSubmit({
      setup_token: tokenRequired ? token.trim() : null,
      name: name.trim(),
      email: email.trim(),
      password,
    });
  };

  return (
    <section data-testid="setup-step-admin" aria-labelledby="setup-title">
      <StepHeading
        id="setup-title"
        title={t("setup.admin.title")}
        lead={t("setup.admin.lead")}
      />
      {failure && field === null && <FailureFrame failure={failure} />}
      <form
        onSubmit={submit}
        className="flex flex-col"
        style={{ gap: 14 }}
        data-testid="setup-admin-form"
      >
        {tokenRequired && (
          <Input
            id={`${uid}-token`}
            label={t("setup.admin.token")}
            name="setup_token"
            autoComplete="off"
            autoFocus
            isMono
            required
            value={token}
            readOnly={pending}
            onChange={(e) => {
              setToken(e.target.value);
            }}
            hint={t("setup.admin.tokenHint")}
            {...errorProp(
              field === "setup_token"
                ? t(setupErrorKey(failure?.code ?? ""))
                : undefined,
            )}
          />
        )}
        <Input
          id={`${uid}-name`}
          label={t("register.name")}
          name="name"
          autoComplete="name"
          autoFocus={!tokenRequired}
          required
          value={name}
          readOnly={pending}
          onChange={(e) => {
            setName(e.target.value);
          }}
        />
        <Input
          id={`${uid}-email`}
          label={t("register.email")}
          type="email"
          name="email"
          autoComplete="username"
          required
          value={email}
          readOnly={pending}
          onChange={(e) => {
            setEmail(e.target.value);
          }}
        />
        <Input
          id={`${uid}-password`}
          label={t("register.password")}
          type="password"
          name="password"
          autoComplete="new-password"
          required
          value={password}
          readOnly={pending}
          onChange={(e) => {
            setPassword(e.target.value);
          }}
          hint={t("register.passwordHint", { count: passwordMin })}
          {...errorProp(
            field === "password"
              ? t(setupErrorKey(failure?.code ?? ""))
              : touched && tooShort
                ? t("register.passwordShort", { count: passwordMin })
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
          readOnly={pending}
          onChange={(e) => {
            setConfirm(e.target.value);
          }}
          {...errorProp(mismatch ? t("register.mismatch") : undefined)}
        />
        <StepActions
          onBack={onBack}
          primary={
            <Button
              type="submit"
              aria-disabled={pending}
              style={{ gap: 8 }}
              data-testid="setup-admin-submit"
            >
              {!pending && <UserCog size={15} aria-hidden />}
              <PendingLabel
                pending={pending}
                idle={t("setup.admin.submit")}
                busy={t("setup.admin.submitting")}
              />
            </Button>
          }
        />
      </form>
    </section>
  );
};
