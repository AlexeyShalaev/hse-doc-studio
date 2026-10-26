import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  useCredentials,
  useGitHosts,
  useHostSettings,
  useSecretsStatus,
} from "@entities/git-remote";
import { describeGitError } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import { AccessCard } from "./AccessCard";
import { CredentialCard } from "./CredentialCard";
import { EncryptionCard } from "./EncryptionCard";
import { FetchDefaultCard } from "./FetchDefaultCard";
import { KnownHostsTable } from "./KnownHostsTable";
import { ServersCard } from "./ServersCard";

type QueryBodyProps = {
  isPending: boolean;
  error: unknown;
  hasData: boolean;
  onRetry: () => void;
  children: ReactNode;
};

// Загрузка и ошибка одним видом для всех блоков раздела.
const QueryBody = ({
  isPending,
  error,
  hasData,
  onRetry,
  children,
}: QueryBodyProps) => {
  const { t } = useTranslation("gitAccess");
  if (hasData) return <>{children}</>;
  if (isPending) {
    return (
      <div
        className="flex items-center"
        role="status"
        style={{ gap: 8, fontSize: 12 }}
      >
        <Spinner size="sm" />
        <span className="dim">{t("access.loading")}</span>
      </div>
    );
  }
  return (
    <Notice
      tone="err"
      role="alert"
      text={describeGitError(error, t("access.loadFailed"))}
      action={
        <button type="button" className="btn xs" onClick={onRetry}>
          {t("access.retry")}
        </button>
      }
    />
  );
};

// Раздел настроек приложения «Доступ к репозиториям»: токены и ключи, доверенные
// серверы, где и как всё это хранится. Якоря нужны поиску по настройкам.
export const GitAccessSection = () => {
  const { t } = useTranslation("gitAccess");
  const credentials = useCredentials();
  const hosts = useGitHosts();
  const hostSettings = useHostSettings();
  const secrets = useSecretsStatus();

  return (
    <>
      <div
        id="git-access"
        className="flex flex-col settings-anchor"
        style={{ gap: 4, marginBottom: 4 }}
      >
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>
          {t("title")}
        </h4>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>
          {t("subtitle")}
        </p>
      </div>

      <div
        className="flex flex-col"
        style={{ gap: 14, paddingBottom: 14, maxWidth: 720 }}
      >
        <AccessCard id="git-access-credentials" title={t("credentials.title")}>
          <QueryBody
            isPending={credentials.isPending}
            error={credentials.error}
            hasData={credentials.data !== undefined}
            onRetry={() => {
              void credentials.refetch();
            }}
          >
            {credentials.data?.length === 0 ? (
              <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
                {t("credentials.empty")}
              </p>
            ) : (
              <ul
                style={{
                  margin: 0,
                  padding: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                {credentials.data?.map((credential) => (
                  <CredentialCard key={credential.id} credential={credential} />
                ))}
              </ul>
            )}
          </QueryBody>
        </AccessCard>

        <AccessCard
          id="git-access-servers"
          title={t("servers.title")}
          description={t("servers.intro")}
        >
          <QueryBody
            isPending={hostSettings.isPending}
            error={hostSettings.error}
            hasData={hostSettings.data !== undefined}
            onRetry={() => {
              void hostSettings.refetch();
            }}
          >
            <ServersCard
              settings={hostSettings.data ?? []}
              credentials={credentials.data ?? []}
            />
          </QueryBody>
        </AccessCard>

        <AccessCard
          id="git-access-hosts"
          title={t("hosts.title")}
          description={t("access.hosts.intro")}
        >
          <QueryBody
            isPending={hosts.isPending}
            error={hosts.error}
            hasData={hosts.data !== undefined}
            onRetry={() => {
              void hosts.refetch();
            }}
          >
            {hosts.data?.length === 0 ? (
              <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
                {t("hosts.empty")}
              </p>
            ) : (
              <KnownHostsTable hosts={hosts.data ?? []} />
            )}
          </QueryBody>
        </AccessCard>

        <QueryBody
          isPending={secrets.isPending}
          error={secrets.error}
          hasData={secrets.data !== undefined}
          onRetry={() => {
            void secrets.refetch();
          }}
        >
          {secrets.data && <EncryptionCard status={secrets.data} />}
        </QueryBody>

        <FetchDefaultCard />
      </div>
    </>
  );
};
