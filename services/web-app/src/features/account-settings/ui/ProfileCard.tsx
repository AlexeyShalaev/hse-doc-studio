import { useId, useState, type FormEvent } from "react";
import { BadgeCheck, Mail, Save, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  Badge,
  Button,
  Input,
  LinkDelivery,
  ResultFrame,
  Spinner,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { validateEmail } from "@entities/profile";
import type { AccountProfile, ChangeEmailResponse } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS } from "../lib/styles";
import { AccountCard } from "./parts";

export type ProfileCardProps = {
  profile: AccountProfile;
  emailVerified: boolean;
  pending?: boolean;
  /** Сообщение сервера о поле name (422). */
  nameIssue?: string | null;
  failure?: Failure | null;
  saved?: boolean;
  onSave: (name: string) => void;
  /** Смена e-mail: состояние запроса и ответ. */
  email: {
    pending?: boolean;
    failure?: Failure | null;
    result?: ChangeEmailResponse | null;
    onSubmit: (input: { email: string; password: string }) => void;
  };
};

const errorProp = (error: string | undefined) => (error ? { error } : {});

/** Имя аккаунта, адрес почты и его смена. */
export const ProfileCard = ({
  profile,
  emailVerified,
  pending = false,
  nameIssue = null,
  failure = null,
  saved = false,
  onSave,
  email,
}: ProfileCardProps) => {
  const { t } = useTranslation("account");
  const uid = useId();
  const [name, setName] = useState(profile.name);
  const [changing, setChanging] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailTouched, setEmailTouched] = useState(false);

  const trimmed = name.replace(/\s+/g, " ").trim();
  const dirty = trimmed !== profile.name;
  const nameError =
    nameIssue ?? (trimmed === "" ? t("profile.nameRequired") : undefined);

  const submitName = (event: FormEvent) => {
    event.preventDefault();
    if (pending || !dirty || trimmed === "") return;
    onSave(trimmed);
  };

  const emailIssue = validateEmail(newEmail);
  const sameEmail =
    newEmail.trim().toLowerCase() === profile.email.toLowerCase();
  const emailCode = email.failure?.code;
  const emailValid = emailIssue === null && !sameEmail && password.length > 0;

  const submitEmail = (event: FormEvent) => {
    event.preventDefault();
    setEmailTouched(true);
    if (email.pending || !emailValid) return;
    email.onSubmit({ email: newEmail.trim(), password });
    setPassword("");
  };

  const sent = email.result ?? null;

  return (
    <AccountCard
      id="account"
      title={t("profile.title")}
      sub={t("profile.sub")}
      testId="account-profile"
    >
      <form
        onSubmit={submitName}
        className="flex flex-col"
        style={{ gap: 12, maxWidth: 420 }}
      >
        <Input
          id="account-name"
          label={t("profile.name")}
          name="name"
          autoComplete="name"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
          }}
          readOnly={pending}
          {...errorProp(dirty || nameIssue ? nameError : undefined)}
        />
        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}
        <div style={ACTIONS}>
          <Button
            type="submit"
            aria-disabled={pending || !dirty}
            style={{ gap: 8 }}
            data-testid="profile-save"
          >
            {pending ? (
              <Spinner size="sm" />
            ) : (
              <Save size={14} aria-hidden="true" />
            )}
            {pending ? t("profile.saving") : t("profile.save")}
          </Button>
          {saved && !dirty && !pending && (
            <span role="status" style={{ fontSize: 12, color: "var(--c-ok)" }}>
              {t("profile.saved")}
            </span>
          )}
        </div>
      </form>

      <div
        id="account-email"
        className="flex flex-col settings-anchor"
        style={{
          gap: 8,
          paddingTop: 12,
          borderTop: "1px dashed var(--border)",
        }}
      >
        <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
          <Mail size={14} aria-hidden="true" style={{ color: "var(--fg-2)" }} />
          <span
            style={{ fontSize: 13, fontWeight: 500 }}
            data-testid="account-email-value"
          >
            {profile.email}
          </span>
          {emailVerified ? (
            <Badge variant="success">
              <BadgeCheck size={11} aria-hidden="true" /> {t("email.verified")}
            </Badge>
          ) : (
            <Badge variant="warning">
              <TriangleAlert size={11} aria-hidden="true" />{" "}
              {t("email.unverified")}
            </Badge>
          )}
          {!changing && (
            <Button
              type="button"
              variant="ghost"
              size="xs"
              onClick={() => {
                setChanging(true);
              }}
            >
              {t("email.change")}
            </Button>
          )}
        </div>

        {changing && !sent && (
          <form
            onSubmit={submitEmail}
            noValidate
            className="flex flex-col"
            style={{ gap: 12, maxWidth: 420 }}
            data-testid="email-form"
          >
            <Input
              id={`${uid}-email`}
              label={t("email.new")}
              type="email"
              name="email"
              autoComplete="email"
              value={newEmail}
              onChange={(e) => {
                setNewEmail(e.target.value);
              }}
              readOnly={email.pending}
              hint={t("email.hint")}
              {...errorProp(
                emailCode === "email_taken"
                  ? t("failure.email_taken")
                  : emailCode === "password_policy"
                    ? undefined
                    : emailTouched && sameEmail
                      ? t("email.same")
                      : emailTouched && emailIssue
                        ? t("email.invalid")
                        : undefined,
              )}
            />
            <Input
              id={`${uid}-password`}
              label={t("email.password")}
              type="password"
              name="current-password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
              }}
              readOnly={email.pending}
              {...errorProp(
                emailCode === "invalid_credentials"
                  ? t("failure.invalid_credentials")
                  : undefined,
              )}
            />
            {email.failure &&
              emailCode !== "email_taken" &&
              emailCode !== "invalid_credentials" && (
                <Notice
                  tone={emailCode === "rate_limited" ? "warn" : "err"}
                  role="alert"
                  text={t(failureKey(email.failure.code))}
                />
              )}
            <div style={ACTIONS}>
              <Button
                type="submit"
                aria-disabled={email.pending}
                style={{ gap: 8 }}
              >
                {email.pending ? (
                  <Spinner size="sm" />
                ) : (
                  <Mail size={14} aria-hidden="true" />
                )}
                {email.pending ? t("email.sending") : t("email.submit")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setChanging(false);
                  setNewEmail("");
                  setPassword("");
                  setEmailTouched(false);
                }}
              >
                {t("email.cancel")}
              </Button>
            </div>
          </form>
        )}

        {changing && sent && (
          <ResultFrame
            tone="info"
            role="status"
            testId="email-sent"
            title={t("email.sent.title", { email: newEmail.trim() })}
            actions={
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={() => {
                  setChanging(false);
                  setNewEmail("");
                }}
              >
                {t("email.sent.close")}
              </Button>
            }
          >
            <span>{t("email.sent.body")}</span>
            {sent.link && <LinkDelivery link={sent.link} kind="verify" once />}
          </ResultFrame>
        )}
      </div>
    </AccountCard>
  );
};
