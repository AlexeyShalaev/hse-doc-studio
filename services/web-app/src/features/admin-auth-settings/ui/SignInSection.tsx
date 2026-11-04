import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { Draft } from "@shared/lib/useDraft";
import { Section, SettingRow } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import type { AdminAuthSettings } from "@entities/session";
import { isLocked } from "../lib/locked";

export type SignInDraft = { password: boolean; passkeys: boolean };

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
  const passkeysLocked = isLocked(settings.fields, "auth.passkeys_enabled");
  const stale = settings.passkey_domains.filter(
    (d) => d.domain !== settings.passkey_domain,
  );
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
        <SettingRow
          label={t("signin.passkeys")}
          hint={
            <>
              {t("signin.passkeysHint")}{" "}
              <span data-testid="auth-passkey-domain">
                {settings.passkey_domain
                  ? t("signin.passkeyDomain", {
                      domain: settings.passkey_domain,
                    })
                  : t("signin.passkeyNoDomain")}
              </span>
            </>
          }
          htmlFor={`${uid}-passkeys`}
          locked={passkeysLocked}
          testId="signin-passkeys-row"
        >
          <Switch
            id={`${uid}-passkeys`}
            checked={draft.value.passkeys}
            disabled={passkeysLocked}
            onChange={(next) => {
              draft.set({ passkeys: next });
            }}
            testId="auth-passkeys-toggle"
          />
        </SettingRow>
        <div
          className="adm-setting-extra flex flex-col"
          style={{ paddingTop: "0.75rem", gap: "0.5rem" }}
        >
          {settings.passkey_issue && (
            <div data-testid="auth-passkey-issue">
              <Notice
                tone="warn"
                text={t(`signin.passkeyIssue.${settings.passkey_issue}`)}
              />
            </div>
          )}
          {stale.length > 0 && (
            <div data-testid="auth-passkey-stale">
              <Notice
                tone="warn"
                text={stale
                  .map((d) =>
                    t("signin.passkeyStale", {
                      count: d.count,
                      domain: d.domain,
                    }),
                  )
                  .join(" ")}
              />
            </div>
          )}
          <p
            style={{ margin: 0, fontSize: "0.71875rem", color: "var(--fg-2)" }}
            data-testid="auth-passkey-address-hint"
          >
            {t("signin.passkeyAddressHint")}
          </p>
        </div>
        {((onlyMethod && !locked) || draft.isChanged("password")) && (
          <div className="adm-setting-extra" style={{ paddingTop: "0.75rem" }}>
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
