import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { SecretsStatus } from "@entities/git-remote";
import { Badge } from "@shared/ui/Badge";
import { Notice } from "@shared/ui/ConflictKit";
import { AccessCard } from "./AccessCard";

export type EncryptionCardProps = {
  status: SecretsStatus;
};

const Fact = ({ children }: { children: ReactNode }) => (
  <li style={{ fontSize: "0.75rem", lineHeight: 1.55, color: "var(--fg-1)" }}>
    {children}
  </li>
);

// Где лежит ключ, которым зашифрованы токены, и что может свести шифрование на
// нет. Предупреждения стоят над фактами: их нельзя пропустить, а спокойное
// состояние выглядит спокойно.
export const EncryptionCard = ({ status }: EncryptionCardProps) => {
  const { t } = useTranslation("gitAccess");
  const shared = status.data_dir_shared_folder ?? null;
  const providerName = shared
    ? t(`sharedProvider.${shared.provider}`, {
        defaultValue: t("sharedProvider.unknown"),
      })
    : "";
  const isFile = status.source === "file";

  return (
    <AccessCard
      id="git-access-encryption"
      title={t("access.encryption.title")}
      description={t("access.encryption.threat")}
    >
      <div className="flex items-center" style={{ gap: "0.5rem" }}>
        <Badge variant={status.ok ? "success" : "error"}>
          {status.ok
            ? t("access.encryption.enabled")
            : t("access.encryption.unavailableChip")}
        </Badge>
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
          {t("access.encryption.stored", { count: status.credentials_total })}
        </span>
      </div>

      {!status.ok && (
        <Notice
          tone="err"
          role="alert"
          text={t("access.encryption.unavailableText")}
        />
      )}
      {status.credentials_unreadable > 0 && (
        <Notice
          tone="err"
          role="alert"
          text={t("access.encryption.unreadable", {
            count: status.credentials_unreadable,
          })}
        />
      )}
      {shared && (
        <Notice
          tone="warn"
          role="status"
          text={
            <>
              {t("access.encryption.sharedFolder", { provider: providerName })}
              <span
                className="mono dim"
                style={{ display: "block", marginTop: "0.25rem" }}
              >
                {t("access.encryption.sharedRoot", { path: shared.root })}
              </span>
            </>
          }
        />
      )}
      {!status.permissions_enforced && (
        <Notice
          tone="warn"
          role="status"
          text={t("access.encryption.permissionsNotEnforced")}
        />
      )}

      <ul
        style={{
          margin: 0,
          paddingLeft: "1.125rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.1875rem",
        }}
      >
        <Fact>
          {isFile
            ? t("access.encryption.sourceFile")
            : t("access.encryption.sourceEnv")}
        </Fact>
        {isFile && status.permissions_enforced && (
          <Fact>{t("access.encryption.permissionsOk")}</Fact>
        )}
      </ul>
    </AccessCard>
  );
};
