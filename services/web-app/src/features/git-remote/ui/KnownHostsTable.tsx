import { useState } from "react";
import { ServerCog } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useDeleteHost, type GitHost } from "@entities/git-remote";
import { describeGitError } from "@entities/git-sync";
import { formatRelativeTime, toast } from "@shared/lib";
import { Modal } from "@shared/ui/Modal";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";

export type KnownHostsTableProps = {
  hosts: GitHost[];
};

const hostLabel = (host: GitHost): string =>
  host.port ? `${host.host}:${String(host.port)}` : host.host;

const cellStyle: React.CSSProperties = {
  padding: "0.5rem 0.625rem",
  textAlign: "left",
  verticalAlign: "top",
  borderBottom: "1px solid var(--border)",
  fontSize: "0.75rem",
};

const headStyle: React.CSSProperties = {
  ...cellStyle,
  fontSize: "0.65625rem",
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--fg-2)",
  verticalAlign: "bottom",
};

// Серверы, ключи которых человек подтвердил. «Забыть» не удаляет ничего ценного:
// при следующем подключении Студия снова покажет отпечаток.
export const KnownHostsTable = ({ hosts }: KnownHostsTableProps) => {
  const { t } = useTranslation("gitAccess");
  const remove = useDeleteHost();
  const [forgetting, setForgetting] = useState<GitHost | null>(null);
  const [error, setError] = useState<string | null>(null);

  const close = (): void => {
    if (remove.isPending) return;
    setForgetting(null);
    setError(null);
  };

  const confirm = (): void => {
    if (!forgetting) return;
    setError(null);
    remove.mutate(
      { host: forgetting.host, port: forgetting.port ?? null },
      {
        onSuccess: () => {
          toast.success(t("access.hosts.forgotten"));
          setForgetting(null);
        },
        onError: (caught) => {
          setError(describeGitError(caught, t("access.hosts.forgetFailed")));
        },
      },
    );
  };

  return (
    <>
      <div style={{ overflowX: "auto" }}>
        <table
          className="tbl-cards"
          data-testid="known-hosts"
          style={{
            width: "100%",
            minWidth: "32.5rem",
            borderCollapse: "collapse",
          }}
        >
          <thead>
            <tr>
              <th scope="col" style={headStyle}>
                {t("access.hosts.columnServer")}
              </th>
              <th scope="col" style={headStyle}>
                {t("access.hosts.columnKeys")}
              </th>
              <th scope="col" style={headStyle}>
                {t("access.hosts.columnAdded")}
              </th>
              <th scope="col" style={{ ...headStyle, width: 1 }}>
                <span className="sr-only">{t("access.hosts.forget")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {hosts.map((host) => (
              <tr key={`${host.host}:${String(host.port ?? "")}`}>
                <th
                  scope="row"
                  className="mono"
                  style={{
                    ...cellStyle,
                    fontWeight: 600,
                    whiteSpace: "nowrap",
                  }}
                >
                  <span
                    className="flex items-center"
                    style={{ gap: "0.375rem" }}
                  >
                    <ServerCog
                      size="0.8125rem"
                      aria-hidden="true"
                      style={{ color: "var(--fg-2)" }}
                    />
                    {hostLabel(host)}
                  </span>
                </th>
                <td data-label={t("access.hosts.columnKeys")} style={cellStyle}>
                  <div className="flex flex-col" style={{ gap: "0.25rem" }}>
                    {host.key_types.length > 0 && (
                      <span
                        className="flex"
                        style={{ gap: "0.25rem", flexWrap: "wrap" }}
                      >
                        {host.key_types.map((type) => (
                          <span key={type} className="chip subtle">
                            {type}
                          </span>
                        ))}
                      </span>
                    )}
                    <ul
                      style={{
                        margin: 0,
                        padding: 0,
                        listStyle: "none",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.125rem",
                      }}
                    >
                      {host.fingerprints_sha256.map((fingerprint) => (
                        <li
                          key={fingerprint}
                          className="mono"
                          style={{
                            fontSize: "0.6875rem",
                            wordBreak: "break-all",
                          }}
                        >
                          {fingerprint}
                        </li>
                      ))}
                    </ul>
                  </div>
                </td>
                <td
                  className="dim"
                  data-label={t("access.hosts.columnAdded")}
                  style={{ ...cellStyle, whiteSpace: "nowrap" }}
                >
                  {formatRelativeTime(host.added_at)}
                </td>
                <td style={{ ...cellStyle, textAlign: "right" }}>
                  <button
                    type="button"
                    className="btn xs"
                    aria-label={t("access.hosts.forgetLabel", {
                      host: hostLabel(host),
                    })}
                    onClick={() => {
                      setForgetting(host);
                    }}
                  >
                    {t("access.hosts.forget")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        isOpen={forgetting !== null}
        onClose={close}
        width={440}
        title={t("access.hosts.forgetTitle", {
          host: forgetting ? hostLabel(forgetting) : "",
        })}
        description={t("access.hosts.forgetText")}
        footer={
          <>
            <button
              type="button"
              className="btn"
              onClick={close}
              disabled={remove.isPending}
            >
              {t("access.hosts.cancel")}
            </button>
            <button
              type="button"
              className="btn danger"
              disabled={remove.isPending}
              onClick={confirm}
            >
              {remove.isPending && <Spinner size="sm" />}
              {t("access.hosts.forgetConfirm")}
            </button>
          </>
        }
      >
        {error !== null ? (
          <Notice tone="err" role="alert" text={error} />
        ) : null}
      </Modal>
    </>
  );
};
