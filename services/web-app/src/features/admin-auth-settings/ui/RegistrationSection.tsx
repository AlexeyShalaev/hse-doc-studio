import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { Draft } from "@shared/lib/useDraft";
import { Input, Section, SettingRow } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import type {
  AdminRegistrationSettings,
  RegistrationMode,
} from "@entities/session";
import { isLocked } from "../lib/locked";
import type { RegistrationDraft } from "../lib/drafts";
import { approvalApplies } from "../lib/validate";

// Порядок от безопасного умолчания к самому открытому.
const MODES: readonly RegistrationMode[] = [
  "invite",
  "domains",
  "open",
  "closed",
];

export type RegistrationSectionProps = {
  settings: AdminRegistrationSettings;
  draft: Draft<RegistrationDraft>;
  /** Ошибка в списке доменов, уже переведённая. */
  domainsError?: string | undefined;
  /** Почта настроена: без неё в режиме доменов новые аккаунты ждут одобрения. */
  smtpEnabled: boolean;
};

/** Кто может зарегистрироваться: режим, домены и одобрение администратором. */
export const RegistrationSection = ({
  settings,
  draft,
  domainsError,
  smtpEnabled,
}: RegistrationSectionProps) => {
  const { t } = useTranslation("adminSettings");
  const uid = useId();
  const modeLocked = isLocked(settings.fields, "auth.registration_mode");
  const domainsLocked = isLocked(settings.fields, "auth.registration_domains");
  const approvalLocked = isLocked(settings.fields, "auth.require_approval");
  const { mode, domains, approval } = draft.value;

  const notes = [
    mode === "domains" && !smtpEnabled && (
      <Notice key="smtp" tone="warn" text={t("registration.noSmtpDomains")} />
    ),
    mode === "open" && !approval && (
      <Notice key="open" tone="warn" text={t("registration.openWarning")} />
    ),
    mode === "closed" && (
      <Notice key="closed" tone="info" text={t("registration.closedNote")} />
    ),
  ].filter(Boolean);

  return (
    <Section
      id="admin-registration"
      testId="admin-registration"
      title={t("registration.title")}
      description={t("registration.sub")}
    >
      <div data-testid="registration-form" style={{ display: "contents" }}>
        <SettingRow
          label={t("registration.modeLabel")}
          locked={modeLocked}
          layout="stacked"
          testId="registration-mode"
        >
          <fieldset className="adm-choices" disabled={modeLocked}>
            <legend className="sr-only">{t("registration.modeLabel")}</legend>
            {MODES.map((value) => {
              const active = mode === value;
              return (
                <label
                  key={value}
                  className="adm-choice"
                  data-testid={`registration-mode-${value}`}
                  data-active={active}
                  data-disabled={modeLocked || undefined}
                >
                  <input
                    type="radio"
                    name={`${uid}-mode`}
                    value={value}
                    checked={active}
                    disabled={modeLocked}
                    onChange={() => {
                      draft.set({ mode: value });
                    }}
                  />
                  <span className="adm-choice-mark" aria-hidden="true" />
                  <span className="adm-choice-title">
                    {t(`registration.mode.${value}.title`)}
                  </span>
                  <span className="adm-choice-body">
                    {t(`registration.mode.${value}.body`)}
                  </span>
                </label>
              );
            })}
          </fieldset>
        </SettingRow>

        {mode === "domains" && (
          <SettingRow
            label={t("registration.domains")}
            hint={t("registration.domainsHint")}
            htmlFor={`${uid}-domains`}
            locked={domainsLocked}
            align="stretch"
            testId="registration-domains"
          >
            <Input
              id={`${uid}-domains`}
              name="domains"
              value={domains}
              readOnly={domainsLocked}
              placeholder="hse.ru, edu.hse.ru"
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => {
                draft.set({ domains: e.target.value });
              }}
              {...(domainsError ? { error: domainsError } : {})}
            />
          </SettingRow>
        )}

        {approvalApplies(mode) && (
          <SettingRow
            label={t("registration.approval")}
            hint={t("registration.approvalHint")}
            htmlFor={`${uid}-approval`}
            locked={approvalLocked}
            testId="registration-approval-row"
          >
            <Switch
              id={`${uid}-approval`}
              checked={approval}
              disabled={approvalLocked}
              onChange={(next) => {
                draft.set({ approval: next });
              }}
              testId="registration-approval"
            />
          </SettingRow>
        )}

        {notes.length > 0 && (
          <div className="adm-setting-extra" style={{ paddingTop: 12 }}>
            {notes}
          </div>
        )}
      </div>
    </Section>
  );
};
