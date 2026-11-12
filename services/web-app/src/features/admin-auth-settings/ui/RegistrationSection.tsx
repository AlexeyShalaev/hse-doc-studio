import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Draft } from "@shared/lib/useDraft";
import { Input, Section, SettingRow, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import type {
  AdminRegistrationSettings,
  RegistrationMode,
} from "@entities/session";
import { isLocked } from "../lib/locked";
import type { RegistrationDraft } from "../lib/drafts";
import { approvalApplies, parseDomains } from "../lib/validate";
import { checkAddress, parseExemptions } from "../lib/approvalExemptions";

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
  /** Ошибки в исключениях из одобрения, по одной на строку, уже переведённые. */
  exemptionsErrors?: readonly string[] | undefined;
  /** Почта настроена: без неё в режиме доменов новые аккаунты ждут одобрения. */
  smtpEnabled: boolean;
};

/** Кто может зарегистрироваться: режим, домены и одобрение администратором. */
export const RegistrationSection = ({
  settings,
  draft,
  domainsError,
  exemptionsErrors = [],
  smtpEnabled,
}: RegistrationSectionProps) => {
  const { t } = useTranslation("adminSettings");
  const uid = useId();
  const modeLocked = isLocked(settings.fields, "auth.registration_mode");
  const domainsLocked = isLocked(settings.fields, "auth.registration_domains");
  const approvalLocked = isLocked(settings.fields, "auth.require_approval");
  const exemptionsLocked = isLocked(
    settings.fields,
    "auth.approval_exemptions",
  );
  const { mode, domains, approval, exemptions } = draft.value;
  const exemptionsShown = approval && approvalApplies(mode);
  const [probe, setProbe] = useState("");
  const check =
    probe.trim() === ""
      ? null
      : checkAddress(probe, {
          mode,
          domains: parseDomains(domains),
          approval,
          rules: parseExemptions(exemptions).rules,
          smtpEnabled,
        });

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
              locked={domainsLocked}
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

        {exemptionsShown && (
          <SettingRow
            label={t("registration.exemptions")}
            hint={t("registration.exemptionsHint")}
            htmlFor={`${uid}-exemptions`}
            locked={exemptionsLocked}
            layout="stacked"
            align="stretch"
            testId="registration-exemptions"
          >
            <div className="flex flex-col" style={{ minWidth: 0 }}>
              <Textarea
                id={`${uid}-exemptions`}
                name="approval_exemptions"
                value={exemptions}
                readOnly={exemptionsLocked}
                rows={Math.min(8, Math.max(3, exemptions.split("\n").length))}
                placeholder={"hse.ru\n*.hse.ru\nname@example.com"}
                autoComplete="off"
                spellCheck={false}
                isMono
                onChange={(e) => {
                  draft.set({ exemptions: e.target.value });
                }}
                data-testid="registration-exemptions-input"
                aria-invalid={exemptionsErrors.length > 0 || undefined}
                aria-describedby={
                  exemptionsErrors.length > 0
                    ? `${uid}-exemptions-errors`
                    : undefined
                }
                className={
                  exemptionsErrors.length > 0 ? "!border-c-err" : undefined
                }
              />
              {exemptionsErrors.length > 0 && (
                <ul
                  id={`${uid}-exemptions-errors`}
                  role="alert"
                  className="text-xs text-c-err"
                  data-testid="registration-exemptions-errors"
                  style={{ marginTop: "0.375rem" }}
                >
                  {exemptionsErrors.map((text) => (
                    <li key={text}>{text}</li>
                  ))}
                </ul>
              )}
              {!smtpEnabled && (
                <div style={{ paddingTop: "0.5rem" }}>
                  <Notice
                    tone="warn"
                    text={t("registration.noSmtpExemptions")}
                  />
                </div>
              )}
            </div>
          </SettingRow>
        )}

        {approvalApplies(mode) && (
          <SettingRow
            label={t("registration.check")}
            hint={t("registration.checkHint")}
            htmlFor={`${uid}-check`}
            align="stretch"
            testId="registration-check"
          >
            <div className="flex flex-col" style={{ minWidth: 0 }}>
              <Input
                id={`${uid}-check`}
                name="check_address"
                type="email"
                value={probe}
                placeholder="name@hse.ru"
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => {
                  setProbe(e.target.value);
                }}
              />
              {check && (
                <p
                  className="hint"
                  role="status"
                  data-testid="registration-check-result"
                  data-kind={check.kind}
                  style={{ marginTop: "0.375rem" }}
                >
                  {t(`registration.checkResult.${check.kind}`, {
                    rule: "rule" in check ? check.rule : "",
                  })}
                </p>
              )}
            </div>
          </SettingRow>
        )}

        {notes.length > 0 && (
          <div className="adm-setting-extra" style={{ paddingTop: "0.75rem" }}>
            {notes}
          </div>
        )}
      </div>
    </Section>
  );
};
