import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input } from "@shared/ui";
import type { RegistrationMode, SetupSettingKey } from "@entities/session";
import { isLocked } from "../lib/locked";
import { parseDomains, type SettingsDraft } from "../lib/steps";
import { LockedBadge, StepActions, StepHeading } from "./parts";

// Порядок от безопасного умолчания к самому открытому.
const MODES: readonly RegistrationMode[] = [
  "invite",
  "domains",
  "open",
  "closed",
];

export type RegistrationStepProps = {
  draft: SettingsDraft;
  /** Ключи, заданные окружением: показаны только для чтения. */
  locked: readonly SetupSettingKey[];
  onChange: (patch: Partial<SettingsDraft>) => void;
  onBack: () => void;
  onNext: () => void;
};

const approvalApplies = (mode: RegistrationMode): boolean =>
  mode === "open" || mode === "domains";

/** Шаг 3: кто может зарегистрироваться. По умолчанию по приглашению. */
export const RegistrationStep = ({
  draft,
  locked,
  onChange,
  onBack,
  onNext,
}: RegistrationStepProps) => {
  const { t } = useTranslation("auth");
  const uid = useId();
  const modeLocked = isLocked(locked, "registration_mode");
  const domainsLocked = isLocked(locked, "registration_domains");
  const approvalLocked = isLocked(locked, "require_approval");
  const domainsMissing =
    draft.registration_mode === "domains" &&
    parseDomains(draft.domains).length === 0;

  return (
    <section
      data-testid="setup-step-registration"
      aria-labelledby="setup-title"
    >
      <StepHeading
        id="setup-title"
        title={t("setup.registration.title")}
        lead={t("setup.registration.lead")}
      />

      <fieldset
        style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
        disabled={modeLocked}
      >
        <legend
          className="flex items-center"
          style={{ gap: 8, padding: 0, marginBottom: 8, fontSize: 12.5 }}
        >
          <span style={{ fontWeight: 600 }}>
            {t("setup.registration.modeLabel")}
          </span>
          {modeLocked && <LockedBadge />}
        </legend>
        <div className="flex flex-col" style={{ gap: 8 }}>
          {MODES.map((mode) => {
            const active = draft.registration_mode === mode;
            return (
              <label
                key={mode}
                data-testid={`setup-mode-${mode}`}
                data-active={active}
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "flex-start",
                  padding: "10px 12px",
                  borderRadius: "var(--r-3)",
                  border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                  background: active ? "var(--accent-soft)" : "var(--bg-1)",
                  cursor: modeLocked ? "default" : "pointer",
                  opacity: modeLocked && !active ? 0.55 : 1,
                }}
              >
                <input
                  type="radio"
                  name={`${uid}-mode`}
                  value={mode}
                  checked={active}
                  disabled={modeLocked}
                  onChange={() => {
                    onChange({ registration_mode: mode });
                  }}
                  style={{ marginTop: 3 }}
                />
                <span className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
                  <span
                    className="flex items-center"
                    style={{ gap: 8, fontSize: 13.5, fontWeight: 500 }}
                  >
                    {t(`setup.registration.mode.${mode}.title`)}
                    {mode === "invite" && (
                      <span className="chip accent">
                        {t("setup.registration.recommended")}
                      </span>
                    )}
                  </span>
                  <span style={{ fontSize: 12.5, color: "var(--fg-2)" }}>
                    {t(`setup.registration.mode.${mode}.body`)}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      {draft.registration_mode === "domains" && (
        <div style={{ marginTop: 14 }} data-testid="setup-domains">
          <Input
            id={`${uid}-domains`}
            label={t("setup.registration.domains")}
            name="domains"
            isMono
            value={draft.domains}
            readOnly={domainsLocked}
            placeholder="hse.ru, edu.hse.ru"
            onChange={(e) => {
              onChange({ domains: e.target.value });
            }}
            {...(domainsMissing
              ? { error: t("setup.registration.domainsRequired") }
              : { hint: t("setup.registration.domainsHint") })}
          />
          {domainsLocked && (
            <div style={{ marginTop: 6 }}>
              <LockedBadge />
            </div>
          )}
        </div>
      )}

      {approvalApplies(draft.registration_mode) && (
        <label
          className="flex"
          style={{ gap: 10, marginTop: 14, alignItems: "flex-start" }}
        >
          <input
            type="checkbox"
            checked={draft.require_approval}
            disabled={approvalLocked}
            onChange={(e) => {
              onChange({ require_approval: e.target.checked });
            }}
            style={{ marginTop: 3 }}
          />
          <span className="flex flex-col" style={{ gap: 2 }}>
            <span
              className="flex items-center"
              style={{ gap: 8, fontSize: 13.5, fontWeight: 500 }}
            >
              {t("setup.registration.approval")}
              {approvalLocked && <LockedBadge />}
            </span>
            <span style={{ fontSize: 12.5, color: "var(--fg-2)" }}>
              {t("setup.registration.approvalHint")}
            </span>
          </span>
        </label>
      )}

      <StepActions
        onBack={onBack}
        primary={
          <Button
            type="button"
            aria-disabled={domainsMissing}
            onClick={() => {
              if (!domainsMissing) onNext();
            }}
            data-testid="setup-next"
          >
            {t("setup.next")}
          </Button>
        }
      />
    </section>
  );
};
