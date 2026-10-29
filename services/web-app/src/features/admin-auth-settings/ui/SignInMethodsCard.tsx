import { useState } from "react";
import { Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, ResultFrame, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminAuthSettings } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS } from "../lib/styles";
import { isLocked } from "../lib/locked";
import { AllLockedNote, LockedBadge, SettingsCard } from "./parts";

export type SignInMethodsCardProps = {
  settings: AdminAuthSettings;
  pending?: boolean;
  failure?: Failure | null;
  saved?: boolean;
  onSave: (passwordEnabled: boolean) => void;
};

/** Способы входа: пароль можно выключить, только если остаётся хотя бы один провайдер. */
export const SignInMethodsCard = ({
  settings,
  pending = false,
  failure = null,
  saved = false,
  onSave,
}: SignInMethodsCardProps) => {
  const { t } = useTranslation("adminSettings");
  const [password, setPassword] = useState(settings.password_enabled);
  const locked = isLocked(settings.fields, "auth.password_enabled");
  const noSso = settings.oidc_enabled_count === 0;
  // Выключить единственный способ входа нельзя: сервер ответит last_login_method.
  const onlyMethod = noSso && settings.password_enabled;
  const dirty = password !== settings.password_enabled;

  return (
    <SettingsCard
      id="admin-signin"
      testId="admin-signin"
      title={t("signin.title")}
      sub={t("signin.sub")}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty && !pending) onSave(password);
        }}
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="signin-form"
      >
        <label className="flex" style={{ gap: 10, alignItems: "flex-start" }}>
          <input
            type="checkbox"
            checked={password}
            disabled={locked || onlyMethod}
            onChange={(e) => {
              setPassword(e.target.checked);
            }}
            style={{ marginTop: 3 }}
            data-testid="signin-password"
          />
          <span className="flex flex-col" style={{ gap: 2 }}>
            <span
              className="flex items-center"
              style={{ gap: 8, fontSize: 13, fontWeight: 500 }}
            >
              {t("signin.password")}
              {locked && <LockedBadge testId="locked-signin-password" />}
            </span>
            <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
              {t("signin.passwordHint")}
            </span>
          </span>
        </label>

        <p
          style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}
          data-testid="signin-sso-count"
        >
          {t("signin.sso", { count: settings.oidc_enabled_count })}
        </p>

        {onlyMethod && !locked && (
          <Notice tone="info" text={t("signin.onlyMethod")} />
        )}
        {!password && dirty && (
          <Notice tone="warn" text={t("signin.disableWarning")} />
        )}
        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}
        {saved && !failure && !dirty && (
          <ResultFrame
            tone="ok"
            role="status"
            testId="signin-saved"
            title={t("saved")}
          />
        )}

        {locked ? (
          <AllLockedNote />
        ) : (
          <div style={ACTIONS}>
            <Button
              type="submit"
              aria-disabled={!dirty || pending}
              style={{ gap: 8 }}
              data-testid="signin-save"
            >
              {pending ? (
                <Spinner size="sm" />
              ) : (
                <Save size={14} aria-hidden="true" />
              )}
              {pending ? t("saving") : t("save")}
            </Button>
          </div>
        )}
      </form>
    </SettingsCard>
  );
};
