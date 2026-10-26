import { useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Check, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { describeGitError } from "@entities/git-sync";
import { initialsOf } from "@shared/lib";
import { Button } from "@shared/ui/Button";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import { ProfileValidationFailed } from "../api/profileApi";
import { useUpdateProfile } from "../api/profileQueries";
import type { Profile } from "../api/profileSchemas";
import {
  PROFILE_EMAIL_MAX,
  PROFILE_NAME_MAX,
  formatCommitAuthor,
  isProfileIssueCode,
  validateProfile,
  type ProfileField,
} from "../lib/validateProfile";

export type ProfileFormProps = {
  /** Сохранённый профиль: начальные значения и признак «подпись общая». */
  profile: Profile;
  /** `section` для настроек, `dialog` для окон подключения и клонирования. */
  variant?: "section" | "dialog";
  /** Подпись главной кнопки. По умолчанию «Сохранить». */
  submitLabel?: string;
  /** Показывает кнопку отмены, если передан обработчик. */
  onCancel?: () => void;
  cancelLabel?: string;
  /** Вызывается после сохранения (и при «Продолжить» без изменений, если allowUnchanged). */
  onSaved?: ((profile: Profile) => void) | undefined;
  /** Разрешает нажать главную кнопку, когда профиль уже задан и не менялся. */
  allowUnchanged?: boolean;
  autoFocus?: boolean;
  /** Идентификаторы-якоря для поиска по настройкам. */
  anchors?: { name?: string; email?: string };
  /** Дополнительные элементы слева от кнопок (например, «Вернуть общую подпись»). */
  actionsStart?: ReactNode;
};

type FieldIssues = Partial<Record<ProfileField, string>>;

const isField = (value: unknown): value is ProfileField =>
  value === "name" || value === "email";

export const ProfileForm = ({
  profile,
  variant = "section",
  submitLabel,
  onCancel,
  cancelLabel,
  onSaved,
  allowUnchanged = false,
  autoFocus = false,
  anchors,
  actionsStart,
}: ProfileFormProps) => {
  const { t } = useTranslation("profile");
  const uid = useId();
  const nameId = `${uid}-name`;
  const emailId = `${uid}-email`;
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const update = useUpdateProfile();

  const [name, setName] = useState(profile.name ?? "");
  const [email, setEmail] = useState(profile.email ?? "");
  const [touched, setTouched] = useState<Record<ProfileField, boolean>>({
    name: false,
    email: false,
  });
  const [submitted, setSubmitted] = useState(false);
  const [serverIssues, setServerIssues] = useState<FieldIssues>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  const check = validateProfile({ name, email });
  const savedName = profile.name ?? "";
  const savedEmail = profile.email ?? "";
  const isDirty = check.name !== savedName || check.email !== savedEmail;
  const isSaving = update.isPending;
  const canSubmit =
    !isSaving && (isDirty || (allowUnchanged && !profile.is_default));

  const messageFor = (field: ProfileField): string | null => {
    const fromServer = serverIssues[field];
    if (fromServer) return fromServer;
    if (!touched[field] && !submitted) return null;
    const code = check.issues[field];
    return code ? t(`validation.${code}`) : null;
  };
  const nameError = messageFor("name");
  const emailError = messageFor("email");

  const edit = (field: ProfileField, value: string) => {
    if (field === "name") setName(value);
    else setEmail(value);
    setServerIssues((prev) => ({ ...prev, [field]: undefined }));
    setServerError(null);
    setJustSaved(false);
  };

  const blur = (field: ProfileField) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
  };

  const handleFailure = (error: unknown) => {
    if (error instanceof ProfileValidationFailed) {
      const next: FieldIssues = {};
      let rest: string | null = null;
      for (const issue of error.issues) {
        const field = issue.loc[issue.loc.length - 1];
        const message = isProfileIssueCode(issue.code)
          ? t(`validation.${issue.code}`)
          : issue.msg;
        if (isField(field)) next[field] ??= message;
        else rest ??= message;
      }
      setServerIssues(next);
      setServerError(rest);
      (next.name ? nameRef : emailRef).current?.focus();
      return;
    }
    setServerError(describeGitError(error, t("form.saveFailed")));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (isSaving) return;
    setSubmitted(true);
    setServerError(null);
    if (!check.isValid) {
      (check.issues.name ? nameRef : emailRef).current?.focus();
      return;
    }
    if (!isDirty) {
      if (allowUnchanged && !profile.is_default) onSaved?.(profile);
      return;
    }
    update.mutate(
      { name: check.name, email: check.email },
      {
        onSuccess: (saved) => {
          setName(saved.name ?? check.name);
          setEmail(saved.email ?? check.email);
          setServerIssues({});
          setJustSaved(true);
          onSaved?.(saved);
        },
        onError: handleFailure,
      },
    );
  };

  const hasPreview = name.trim() !== "" || email.trim() !== "";
  const previewText = formatCommitAuthor(check.name, check.email);
  const compact = variant === "dialog";

  return (
    <form
      noValidate
      onSubmit={submit}
      aria-busy={isSaving}
      className="flex flex-col"
      style={{ gap: compact ? 14 : 16 }}
      data-testid="profile-form"
    >
      {profile.is_default && !compact && (
        <Notice
          tone="warn"
          role="status"
          text={t("form.defaultNotice", {
            author: profile.commit_preview,
          })}
        />
      )}

      <div className="flex flex-col" style={{ gap: 14 }}>
        <div
          id={anchors?.name}
          className={anchors?.name ? "field settings-anchor" : "field"}
        >
          <label htmlFor={nameId}>{t("form.name")}</label>
          <input
            ref={nameRef}
            id={nameId}
            className={nameError ? "input !border-c-err" : "input"}
            value={name}
            placeholder={t("form.namePlaceholder")}
            autoComplete="name"
            autoFocus={autoFocus}
            readOnly={isSaving}
            maxLength={PROFILE_NAME_MAX * 2}
            aria-invalid={nameError ? true : undefined}
            aria-describedby={nameError ? `${nameId}-error` : undefined}
            onChange={(e) => {
              edit("name", e.target.value);
            }}
            onBlur={() => {
              blur("name");
            }}
          />
          {nameError && (
            <p
              id={`${nameId}-error`}
              className="text-xs text-c-err"
              role="alert"
            >
              {nameError}
            </p>
          )}
        </div>

        <div
          id={anchors?.email}
          className={anchors?.email ? "field settings-anchor" : "field"}
        >
          <label htmlFor={emailId}>{t("form.email")}</label>
          <input
            ref={emailRef}
            id={emailId}
            type="email"
            inputMode="email"
            className={emailError ? "input !border-c-err" : "input"}
            value={email}
            placeholder={t("form.emailPlaceholder")}
            autoComplete="email"
            spellCheck={false}
            readOnly={isSaving}
            maxLength={PROFILE_EMAIL_MAX * 2}
            aria-invalid={emailError ? true : undefined}
            aria-describedby={
              emailError ? `${emailId}-error` : `${emailId}-hint`
            }
            onChange={(e) => {
              edit("email", e.target.value);
            }}
            onBlur={() => {
              blur("email");
            }}
          />
          {emailError ? (
            <p
              id={`${emailId}-error`}
              className="text-xs text-c-err"
              role="alert"
            >
              {emailError}
            </p>
          ) : (
            <p id={`${emailId}-hint`} className="hint">
              {t("form.noreplyHint")}
            </p>
          )}
        </div>
      </div>

      <div
        className="flex flex-col"
        style={{ gap: 6 }}
        data-testid="profile-preview"
      >
        <span
          className="dim"
          style={{
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          {t("form.preview")}
        </span>
        <div
          className="flex items-center"
          style={{
            gap: 10,
            padding: "9px 12px",
            borderRadius: "var(--r-2)",
            border: "1px solid var(--border)",
            background: "var(--bg-2)",
            minWidth: 0,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              width: 26,
              height: 26,
              borderRadius: "50%",
              flexShrink: 0,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 10,
              fontWeight: 700,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              border: "1px solid var(--accent-line)",
            }}
          >
            {hasPreview ? initialsOf(check.name) || "?" : "?"}
          </span>
          <span
            className="mono truncate"
            style={{
              fontSize: 12.5,
              color: hasPreview ? "var(--fg-0)" : "var(--fg-3)",
              minWidth: 0,
            }}
            title={hasPreview ? previewText : undefined}
          >
            {hasPreview ? previewText : t("form.previewEmpty")}
          </span>
        </div>
      </div>

      <div
        className="flex items-start"
        style={{
          gap: 8,
          fontSize: 11.5,
          lineHeight: 1.5,
          color: "var(--fg-2)",
        }}
      >
        <ShieldAlert
          size={13}
          aria-hidden="true"
          style={{ flexShrink: 0, marginTop: 2 }}
        />
        <span>{t("form.privacy")}</span>
      </div>

      {serverError && (
        <Notice
          tone="err"
          role="alert"
          text={serverError}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                setServerError(null);
              }}
            >
              {t("form.dismiss")}
            </button>
          }
        />
      )}

      <div
        className="flex items-center"
        style={{
          gap: 10,
          justifyContent: compact ? "flex-end" : "flex-start",
          flexWrap: "wrap",
        }}
      >
        {actionsStart && (
          <div style={{ marginRight: compact ? "auto" : 0 }}>
            {actionsStart}
          </div>
        )}
        {justSaved && !isSaving && (
          <span
            role="status"
            className="flex items-center"
            style={{ gap: 5, fontSize: 12, color: "var(--c-ok)" }}
          >
            <Check size={13} aria-hidden="true" />
            {t("form.saved")}
          </span>
        )}
        {onCancel && (
          <Button
            type="button"
            variant="ghost"
            disabled={isSaving}
            onClick={onCancel}
          >
            {cancelLabel ?? t("form.cancel")}
          </Button>
        )}
        <Button type="submit" variant="primary" disabled={!canSubmit}>
          {isSaving ? (
            <>
              <Spinner size="sm" />
              {t("form.saving")}
            </>
          ) : (
            (submitLabel ?? t("form.save"))
          )}
        </Button>
      </div>
    </form>
  );
};
