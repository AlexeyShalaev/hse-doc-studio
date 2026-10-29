import { useId, useState, type FormEvent } from "react";
import {
  GitCommitHorizontal,
  Save,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { validateEmail } from "@entities/profile";
import type { AccountProfile } from "@entities/session";
import type { AccountPatch } from "../api/accountApi";
import {
  isDirty,
  modeOf,
  patchFor,
  previewOf,
  type CommitMode,
} from "../lib/commitIdentity";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS, HINT } from "../lib/styles";
import { AccountCard } from "./parts";

export type CommitIdentityCardProps = {
  profile: AccountProfile;
  pending?: boolean;
  /** Сообщения сервера по полям commit_name и commit_email (422). */
  issues?: { commit_name?: string; commit_email?: string };
  failure?: Failure | null;
  saved?: boolean;
  onSave: (patch: AccountPatch) => void;
};

const MODES: CommitMode[] = ["noreply", "account", "own"];

const errorProp = (error: string | undefined) => (error ? { error } : {});

/**
 * Подпись версий: имя и адрес, которые попадают в коммиты. Коммит остаётся во
 * внешнем репозитории навсегда, поэтому настоящий адрес уходит туда только по
 * явному выбору человека.
 */
export const CommitIdentityCard = ({
  profile,
  pending = false,
  issues = {},
  failure = null,
  saved = false,
  onSave,
}: CommitIdentityCardProps) => {
  const { t } = useTranslation("account");
  const uid = useId();
  const [mode, setMode] = useState<CommitMode>(modeOf(profile));
  const [commitName, setCommitName] = useState(profile.commit_name ?? "");
  const [ownEmail, setOwnEmail] = useState(profile.commit_email ?? "");
  const [touched, setTouched] = useState(false);

  const dirty = isDirty(profile, mode, commitName, ownEmail);
  const ownIssue =
    mode === "own" && validateEmail(ownEmail) !== null
      ? t("commit.ownInvalid")
      : undefined;
  const preview = previewOf(mode, profile, commitName, ownEmail);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (pending || !dirty || ownIssue) return;
    onSave(patchFor(mode, commitName, ownEmail));
  };

  return (
    <AccountCard
      id="account-commit"
      title={t("commit.title")}
      sub={t("commit.sub")}
      testId="account-commit"
    >
      <form
        onSubmit={submit}
        noValidate
        className="flex flex-col"
        style={{ gap: 14, maxWidth: 520 }}
        data-testid="commit-form"
      >
        <Input
          id={`${uid}-name`}
          label={t("commit.name")}
          name="commit-name"
          value={commitName}
          placeholder={profile.name}
          onChange={(e) => {
            setCommitName(e.target.value);
          }}
          readOnly={pending}
          hint={t("commit.nameHint")}
          {...errorProp(issues.commit_name)}
        />

        <fieldset
          style={{ border: 0, margin: 0, padding: 0 }}
          className="flex flex-col"
          disabled={pending}
        >
          <legend style={{ fontSize: 12.5, fontWeight: 500, marginBottom: 8 }}>
            {t("commit.emailLegend")}
          </legend>
          <div role="radiogroup" className="flex flex-col" style={{ gap: 8 }}>
            {MODES.map((value) => {
              const id = `${uid}-mode-${value}`;
              const checked = mode === value;
              return (
                <label
                  key={value}
                  htmlFor={id}
                  className="flex"
                  data-checked={checked ? "true" : undefined}
                  style={{
                    gap: 10,
                    alignItems: "flex-start",
                    padding: "10px 12px",
                    borderRadius: "var(--r-2)",
                    border: `1px solid ${checked ? "var(--accent)" : "var(--border)"}`,
                    background: checked ? "var(--bg-2)" : "transparent",
                    cursor: "pointer",
                  }}
                >
                  <input
                    id={id}
                    type="radio"
                    name={`${uid}-mode`}
                    checked={checked}
                    onChange={() => {
                      setMode(value);
                    }}
                    style={{ marginTop: 3 }}
                  />
                  <span
                    className="flex flex-col"
                    style={{ gap: 2, minWidth: 0 }}
                  >
                    <span style={{ fontSize: 13, fontWeight: 600 }}>
                      {t(`commit.modes.${value}.title`)}
                      {value === "noreply" && (
                        <span className="chip accent" style={{ marginLeft: 8 }}>
                          {t("commit.recommended")}
                        </span>
                      )}
                    </span>
                    <span style={HINT}>{t(`commit.modes.${value}.hint`)}</span>
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        {mode === "own" && (
          <Input
            id={`${uid}-own-email`}
            label={t("commit.ownEmail")}
            type="email"
            name="commit-email"
            autoComplete="off"
            value={ownEmail}
            onChange={(e) => {
              setOwnEmail(e.target.value);
            }}
            readOnly={pending}
            {...errorProp(
              issues.commit_email ?? (touched ? ownIssue : undefined),
            )}
          />
        )}

        {mode === "noreply" ? (
          <Notice
            tone="info"
            text={
              <span className="flex items-center" style={{ gap: 6 }}>
                <ShieldCheck size={13} aria-hidden="true" />
                {t("commit.privateNote")}
              </span>
            }
          />
        ) : (
          <Notice
            tone="warn"
            role="status"
            text={
              <span className="flex items-center" style={{ gap: 6 }}>
                <TriangleAlert size={13} aria-hidden="true" />
                {t("commit.publicNote")}
              </span>
            }
          />
        )}

        <div className="flex flex-col" style={{ gap: 4 }}>
          <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
            {t("commit.preview")}
          </span>
          <code
            data-testid="commit-preview"
            className="flex items-center"
            style={{
              gap: 8,
              fontSize: 12.5,
              padding: "8px 10px",
              borderRadius: "var(--r-2)",
              background: "var(--bg-2)",
              overflowWrap: "anywhere",
            }}
          >
            <GitCommitHorizontal
              size={14}
              aria-hidden="true"
              style={{ flexShrink: 0 }}
            />
            {preview}
          </code>
        </div>

        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}

        <div style={ACTIONS}>
          <Button
            type="submit"
            aria-disabled={pending || !dirty}
            style={{ gap: 8 }}
            data-testid="commit-save"
          >
            {pending ? (
              <Spinner size="sm" />
            ) : (
              <Save size={14} aria-hidden="true" />
            )}
            {pending ? t("commit.saving") : t("commit.save")}
          </Button>
          {saved && !dirty && !pending && (
            <span role="status" style={{ fontSize: 12, color: "var(--c-ok)" }}>
              {t("commit.saved")}
            </span>
          )}
        </div>
      </form>
    </AccountCard>
  );
};
