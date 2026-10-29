import { useId, useState } from "react";
import { Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, ResultFrame, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  AdminRegistrationSettings,
  RegistrationMode,
  UpdateAdminRegistrationRequest,
} from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS } from "../lib/styles";
import { approvalApplies, invalidDomains, parseDomains } from "../lib/validate";
import { isLocked } from "../lib/locked";
import { AllLockedNote, LockedBadge, SettingsCard } from "./parts";

// Порядок от безопасного умолчания к самому открытому.
const MODES: readonly RegistrationMode[] = [
  "invite",
  "domains",
  "open",
  "closed",
];

export type RegistrationCardProps = {
  settings: AdminRegistrationSettings;
  /** Почта настроена: без неё в режиме доменов новые аккаунты ждут одобрения. */
  smtpEnabled: boolean;
  pending?: boolean;
  failure?: Failure | null;
  saved?: boolean;
  onSave: (patch: UpdateAdminRegistrationRequest) => void;
};

/** Кто может зарегистрироваться: режим, домены и одобрение администратором. */
export const RegistrationCard = ({
  settings,
  smtpEnabled,
  pending = false,
  failure = null,
  saved = false,
  onSave,
}: RegistrationCardProps) => {
  const { t } = useTranslation("adminSettings");
  const uid = useId();
  const [mode, setMode] = useState(settings.registration_mode);
  const [domains, setDomains] = useState(
    settings.registration_domains.join(", "),
  );
  const [approval, setApproval] = useState(settings.require_approval);

  const modeLocked = isLocked(settings.fields, "auth.registration_mode");
  const domainsLocked = isLocked(settings.fields, "auth.registration_domains");
  const approvalLocked = isLocked(settings.fields, "auth.require_approval");
  const allLocked = modeLocked && domainsLocked && approvalLocked;

  const parsed = parseDomains(domains);
  const bad = invalidDomains(parsed);
  const domainsError =
    mode === "domains" && !domainsLocked
      ? parsed.length === 0
        ? t("registration.domainsRequired")
        : bad.length > 0
          ? t("registration.domainsInvalid", { list: bad.join(", ") })
          : undefined
      : undefined;

  const dirty =
    (!modeLocked && mode !== settings.registration_mode) ||
    (!domainsLocked &&
      parsed.join(",") !== settings.registration_domains.join(",")) ||
    (!approvalLocked && approval !== settings.require_approval);
  const canSave = dirty && !domainsError && !pending;

  const submit = () => {
    if (!canSave) return;
    onSave({
      registration_mode:
        !modeLocked && mode !== settings.registration_mode ? mode : null,
      registration_domains:
        !domainsLocked &&
        parsed.join(",") !== settings.registration_domains.join(",")
          ? parsed
          : null,
      require_approval:
        !approvalLocked && approval !== settings.require_approval
          ? approval
          : null,
    });
  };

  return (
    <SettingsCard
      id="admin-registration"
      testId="admin-registration"
      title={t("registration.title")}
      sub={t("registration.sub")}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex flex-col"
        style={{ gap: 14 }}
        data-testid="registration-form"
      >
        <fieldset
          style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
          disabled={modeLocked}
        >
          <legend
            className="flex items-center"
            style={{ gap: 8, padding: 0, marginBottom: 8, fontSize: 12.5 }}
          >
            <span style={{ fontWeight: 600 }}>
              {t("registration.modeLabel")}
            </span>
            {modeLocked && <LockedBadge testId="locked-registration-mode" />}
          </legend>
          <div className="flex flex-col" style={{ gap: 8 }}>
            {MODES.map((value) => {
              const active = mode === value;
              return (
                <label
                  key={value}
                  data-testid={`registration-mode-${value}`}
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
                    value={value}
                    checked={active}
                    disabled={modeLocked}
                    onChange={() => {
                      setMode(value);
                    }}
                    style={{ marginTop: 3 }}
                  />
                  <span
                    className="flex flex-col"
                    style={{ gap: 2, minWidth: 0 }}
                  >
                    <span style={{ fontSize: 13, fontWeight: 500 }}>
                      {t(`registration.mode.${value}.title`)}
                    </span>
                    <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
                      {t(`registration.mode.${value}.body`)}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        {mode === "domains" && (
          <div data-testid="registration-domains">
            <Input
              id={`${uid}-domains`}
              label={t("registration.domains")}
              name="domains"
              isMono
              value={domains}
              readOnly={domainsLocked}
              placeholder="hse.ru, edu.hse.ru"
              onChange={(e) => {
                setDomains(e.target.value);
              }}
              {...(domainsError
                ? { error: domainsError }
                : { hint: t("registration.domainsHint") })}
            />
            {domainsLocked && (
              <div style={{ marginTop: 6 }}>
                <LockedBadge testId="locked-registration-domains" />
              </div>
            )}
          </div>
        )}

        {approvalApplies(mode) && (
          <label className="flex" style={{ gap: 10, alignItems: "flex-start" }}>
            <input
              type="checkbox"
              checked={approval}
              disabled={approvalLocked}
              onChange={(e) => {
                setApproval(e.target.checked);
              }}
              style={{ marginTop: 3 }}
              data-testid="registration-approval"
            />
            <span className="flex flex-col" style={{ gap: 2 }}>
              <span
                className="flex items-center"
                style={{ gap: 8, fontSize: 13, fontWeight: 500 }}
              >
                {t("registration.approval")}
                {approvalLocked && (
                  <LockedBadge testId="locked-registration-approval" />
                )}
              </span>
              <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
                {t("registration.approvalHint")}
              </span>
            </span>
          </label>
        )}

        {mode === "domains" && !smtpEnabled && (
          <Notice tone="warn" text={t("registration.noSmtpDomains")} />
        )}
        {mode === "open" && !approval && (
          <Notice tone="warn" text={t("registration.openWarning")} />
        )}
        {mode === "closed" && (
          <Notice tone="info" text={t("registration.closedNote")} />
        )}

        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}
        {saved && !failure && !dirty && (
          <ResultFrame
            tone="ok"
            role="status"
            testId="registration-saved"
            title={t("saved")}
          />
        )}

        {allLocked ? (
          <AllLockedNote />
        ) : (
          <div style={ACTIONS}>
            <Button
              type="submit"
              aria-disabled={!canSave}
              style={{ gap: 8 }}
              data-testid="registration-save"
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
