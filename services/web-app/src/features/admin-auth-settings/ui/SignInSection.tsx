import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { Draft } from "@shared/lib/useDraft";
import { Section, SettingRow } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import type { AdminAuthSettings } from "@entities/session";
import { isLocked } from "../lib/locked";

export type SignInDraft = { password: boolean };

export type SignInSectionProps = {
  settings: AdminAuthSettings;
  draft: Draft<SignInDraft>;
};

/** Способы входа: пароль можно выключить, только если остаётся хотя бы один провайдер. */
export const SignInSection = ({ settings, draft }: SignInSectionProps) => {
  const { t } = useTranslation("adminSettings");
  const uid = useId();
  const locked = isLocked(settings.fields, "auth.password_enabled");
  // Выключить единственный способ входа нельзя: сервер ответит last_login_method.
  const onlyMethod =
    settings.oidc_enabled_count === 0 && settings.password_enabled;
  const password = draft.value.password;
  const toggle = (
    <Switch
      id={`${uid}-password`}
      checked={password}
      disabled={locked || onlyMethod}
      onChange={(next) => {
        draft.set({ password: next });
      }}
      describedBy={`${uid}-sso`}
      testId="signin-password"
    />
  );

  return (
    <Section
      id="admin-signin"
      testId="admin-signin"
      title={t("signin.title")}
      description={t("signin.sub")}
    >
      <div data-testid="signin-form" style={{ display: "contents" }}>
        <SettingRow
          label={t("signin.password")}
          hint={
            <>
              {t("signin.passwordHint")}{" "}
              <span id={`${uid}-sso`} data-testid="signin-sso-count">
                {t("signin.sso", { count: settings.oidc_enabled_count })}
              </span>
            </>
          }
          htmlFor={`${uid}-password`}
          locked={locked}
          testId="signin-password-row"
        >
          {toggle}
        </SettingRow>
        {((onlyMethod && !locked) || draft.isChanged("password")) && (
          <div className="adm-setting-extra" style={{ paddingTop: 12 }}>
            {onlyMethod && !locked && (
              <Notice tone="info" text={t("signin.onlyMethod")} />
            )}
            {!password && draft.isChanged("password") && (
              <Notice tone="warn" text={t("signin.disableWarning")} />
            )}
          </div>
        )}
      </div>
    </Section>
  );
};
