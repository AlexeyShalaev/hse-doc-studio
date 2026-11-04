import { Lock, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { GitCredential } from "@entities/git-remote";
import { formatRelativeTime } from "@shared/lib";
import { CredentialStatusChip } from "./CredentialStatusChip";
import { ExpiryBadge } from "./ExpiryBadge";

export const NEW_CREDENTIAL = "new";

export type CredentialPickerProps = {
  credentials: GitCredential[];
  /** Id выбранного доступа или NEW_CREDENTIAL. */
  value: string;
  onChange: (value: string) => void;
  host: string;
};

const rowStyle = (active: boolean): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: "0.625rem",
  padding: "0.5rem 0.625rem",
  borderRadius: "var(--r-2)",
  border: `1px solid ${active ? "var(--accent-line)" : "var(--border)"}`,
  background: active ? "var(--accent-soft)" : "var(--bg-1)",
  cursor: "pointer",
  fontSize: "0.78125rem",
});

// «Уже есть токен для этого сервера»: выбираем сохранённый доступ или заводим
// новый. Сами токены сюда не приходят, только метка, начало вида и итог проверки.
export const CredentialPicker = ({
  credentials,
  value,
  onChange,
  host,
}: CredentialPickerProps) => {
  const { t } = useTranslation("gitAccess");
  return (
    <div
      role="radiogroup"
      aria-label={t("picker.label", { host })}
      className="flex flex-col"
      style={{ gap: "0.375rem" }}
      data-testid="credential-picker"
    >
      {credentials.map((credential) => (
        <label key={credential.id} style={rowStyle(credential.id === value)}>
          <input
            type="radio"
            name="credential"
            checked={credential.id === value}
            onChange={() => {
              onChange(credential.id);
            }}
            style={{ accentColor: "var(--accent)" }}
          />
          <Lock
            size="0.8125rem"
            aria-hidden="true"
            style={{ color: "var(--fg-2)", flexShrink: 0 }}
          />
          <span style={{ flex: 1, minWidth: 0 }}>
            <span className="truncate" style={{ display: "block" }}>
              {credential.label}
            </span>
            <span
              className="dim truncate"
              style={{ display: "block", fontSize: "0.6875rem" }}
            >
              {credential.token_family ? `${credential.token_family}… · ` : ""}
              {credential.last_used_at
                ? t("picker.lastUsed", {
                    when: formatRelativeTime(credential.last_used_at),
                  })
                : t("picker.neverUsed")}
            </span>
          </span>
          <ExpiryBadge expiresAt={credential.expires_at} />
          <CredentialStatusChip status={credential.status} />
        </label>
      ))}
      <label style={rowStyle(value === NEW_CREDENTIAL)}>
        <input
          type="radio"
          name="credential"
          checked={value === NEW_CREDENTIAL}
          onChange={() => {
            onChange(NEW_CREDENTIAL);
          }}
          style={{ accentColor: "var(--accent)" }}
        />
        <Plus
          size="0.8125rem"
          aria-hidden="true"
          style={{ color: "var(--fg-2)", flexShrink: 0 }}
        />
        <span>{t("picker.addNew")}</span>
      </label>
    </div>
  );
};
