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
          style={{
            gap: "0.5rem",
            padding: 0,
            marginBottom: "0.5rem",
            fontSize: "0.78125rem",
          }}
        >
          <span style={{ fontWeight: 600 }}>
            {t("setup.registration.modeLabel")}
          </span>
          {modeLocked && <LockedBadge />}
        </legend>
        <div className="flex flex-col" style={{ gap: "0.5rem" }}>
          {MODES.map((mode) => {
            const active = draft.registration_mode === mode;
            return (
              <label
                key={mode}
                data-testid={`setup-mode-${mode}`}
                data-active={active}
                style={{
                  display: "flex",
                  gap: "0.625rem",
                  alignItems: "flex-start",
                  padding: "0.625rem 0.75rem",
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
                  style={{ marginTop: "0.1875rem" }}
                />
                <span
                  className="flex flex-col"
                  style={{ gap: "0.125rem", minWidth: 0 }}
                >
                  <span
                    className="flex items-center"
                    style={{
                      gap: "0.5rem",
                      fontSize: "0.84375rem",
                      fontWeight: 500,
                    }}
                  >
                    {t(`setup.registration.mode.${mode}.title`)}
                    {mode === "invite" && (
                      <span className="chip accent">
                        {t("setup.registration.recommended")}
                      </span>
                    )}
                  </span>
                  <span
                    style={{ fontSize: "0.78125rem", color: "var(--fg-2)" }}
                  >
                    {t(`setup.registration.mode.${mode}.body`)}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      {draft.registration_mode === "domains" && (
        <div style={{ marginTop: "0.875rem" }} data-testid="setup-domains">
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
            <div style={{ marginTop: "0.375rem" }}>
              <LockedBadge />
            </div>
          )}
        </div>
      )}

      {approvalApplies(draft.registration_mode) && (
        <label
          className="flex"
          style={{
            gap: "0.625rem",
            marginTop: "0.875rem",
            alignItems: "flex-start",
          }}
        >
          <input
            type="checkbox"
            checked={draft.require_approval}
            disabled={approvalLocked}
            onChange={(e) => {
              onChange({ require_approval: e.target.checked });
            }}
            style={{ marginTop: "0.1875rem" }}
          />
          <span className="flex flex-col" style={{ gap: "0.125rem" }}>
            <span
              className="flex items-center"
              style={{ gap: "0.5rem", fontSize: "0.84375rem", fontWeight: 500 }}
            >
              {t("setup.registration.approval")}
              {approvalLocked && <LockedBadge />}
            </span>
            <span style={{ fontSize: "0.78125rem", color: "var(--fg-2)" }}>
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
