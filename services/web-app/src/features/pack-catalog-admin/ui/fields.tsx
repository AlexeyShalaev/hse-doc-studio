import { useId, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useCredentials } from "@entities/git-remote";
import { usePackServiceAccess } from "@entities/pack-studio";
import { hostOfUrl } from "@features/pack-workspaces/lib/hostOfUrl";
import { Select } from "@shared/ui";
import type { AccessChoice } from "../lib/access";

/** Галочка с подписью и пояснением под ней. */
export const CheckField = ({
  checked,
  onChange,
  label,
  hint,
  disabled = false,
  testId,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: string | undefined;
  disabled?: boolean;
  testId?: string | undefined;
}) => {
  const id = useId();
  return (
    <div className="flex flex-col" style={{ gap: "0.125rem" }}>
      <label
        htmlFor={id}
        className="flex items-center"
        style={{ gap: "0.5rem", fontSize: "0.75rem" }}
      >
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => {
            onChange(e.target.checked);
          }}
          style={{ accentColor: "var(--accent)" }}
          data-testid={testId}
        />
        {label}
      </label>
      {hint && (
        <p className="hint" style={{ marginLeft: "1.5rem" }}>
          {hint}
        </p>
      )}
    </div>
  );
};

type AccessKind = AccessChoice["kind"];

/**
 * Доступ к репозиторию источника: без доступа, личный доступ админа из «Доступов git»
 * (с тем же хостом, что у адреса) или служебный доступ установки.
 */
export const AccessPicker = ({
  url,
  value,
  onChange,
  enabled,
}: {
  url: string;
  value: AccessChoice;
  onChange: (next: AccessChoice) => void;
  /** Окно открыто: списки доступов грузятся только тогда. */
  enabled: boolean;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  const credentials = useCredentials(enabled);
  const service = usePackServiceAccess();
  const kindId = useId();
  const itemId = useId();
  const host = hostOfUrl(url);

  const credentialOptions = useMemo(
    () =>
      (credentials.data ?? [])
        .filter((c) => host === null || c.host.toLowerCase() === host)
        .map((c) => ({ value: c.id, label: `${c.label} · ${c.host}` })),
    [credentials.data, host],
  );
  const serviceOptions = useMemo(
    () =>
      (service.data ?? []).map((s) => ({
        value: s.id,
        label: `${s.label} · ${s.url}`,
      })),
    [service.data],
  );

  const setKind = (kind: AccessKind) => {
    if (kind === "none") onChange({ kind });
    else if (kind === "personal") {
      onChange({ kind, credentialId: credentialOptions[0]?.value ?? null });
    } else {
      onChange({ kind, serviceAccessId: serviceOptions[0]?.value ?? null });
    }
  };

  const items = value.kind === "personal" ? credentialOptions : serviceOptions;
  const selected =
    value.kind === "personal"
      ? value.credentialId
      : value.kind === "service"
        ? value.serviceAccessId
        : null;

  return (
    <div className="flex flex-col" style={{ gap: "0.5rem" }}>
      <div className="field">
        <label htmlFor={kindId}>{t("add.access")}</label>
        <Select
          id={kindId}
          value={value.kind}
          onValueChange={(next) => {
            setKind(next as AccessKind);
          }}
          options={[
            { value: "none", label: t("add.accessNone") },
            { value: "personal", label: t("add.accessPersonal") },
            { value: "service", label: t("add.accessService") },
          ]}
          ariaLabel={t("add.access")}
        />
      </div>
      {value.kind !== "none" && (
        <div className="field">
          <label htmlFor={itemId}>
            {value.kind === "personal" ? t("add.credential") : t("add.service")}
          </label>
          {items.length === 0 ? (
            <p className="hint" data-testid="pc-access-empty">
              {value.kind === "personal"
                ? t("add.credentialEmpty")
                : t("add.serviceEmpty")}
            </p>
          ) : (
            <Select
              id={itemId}
              value={selected ?? ""}
              placeholder={t("add.choose")}
              onValueChange={(next) => {
                onChange(
                  value.kind === "personal"
                    ? { kind: "personal", credentialId: next }
                    : { kind: "service", serviceAccessId: next },
                );
              }}
              options={items}
              ariaLabel={
                value.kind === "personal"
                  ? t("add.credential")
                  : t("add.service")
              }
            />
          )}
        </div>
      )}
    </div>
  );
};
