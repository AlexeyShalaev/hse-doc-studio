import { useState } from "react";
import { Plus, Server } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  providerOfHost,
  worstExpiry,
  type GitCredential,
  type GitHostSettings,
} from "@entities/git-remote";
import { shortVersion } from "../lib/formatDate";
import { ExpiryBadge } from "./ExpiryBadge";
import { HostSettingsDialog } from "./HostSettingsDialog";

export type ServersCardProps = {
  settings: GitHostSettings[];
  credentials: GitCredential[];
};

const hostLabel = (host: string, port: number | null | undefined): string =>
  port ? `${host}:${String(port)}` : host;

type Row = {
  key: string;
  settings: GitHostSettings;
  credentials: GitCredential[];
};

// Серверы, с которыми работает Студия: что за сервер и как это узнали, свой
// сертификат центра выдачи, закреплённый сертификат и токены с их сроками.
export const ServersCard = ({ settings, credentials }: ServersCardProps) => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const [editing, setEditing] = useState<GitHostSettings | "new" | null>(null);

  const rows: Row[] = settings.map((item) => ({
    key: hostLabel(item.host.toLowerCase(), item.port),
    settings: item,
    credentials: credentials.filter(
      (credential) => credential.host.toLowerCase() === item.host.toLowerCase(),
    ),
  }));
  // Токен есть, а настроек у сервера нет: показываем и его, определение по имени хоста.
  const known = new Set(rows.map((row) => row.settings.host.toLowerCase()));
  for (const credential of credentials) {
    const host = credential.host.toLowerCase();
    if (known.has(host)) continue;
    known.add(host);
    const detection = providerOfHost(host, null, undefined);
    rows.push({
      key: host,
      settings: {
        host,
        port: null,
        provider_override: null,
        provider_info: detection,
        ca_present: false,
        pinned_fingerprint: null,
      },
      credentials: credentials.filter((c) => c.host.toLowerCase() === host),
    });
  }

  return (
    <>
      <div className="flex flex-col" style={{ gap: 10 }}>
        {rows.length === 0 ? (
          <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
            {t("servers.empty")}
          </p>
        ) : (
          <ul
            data-testid="servers-list"
            style={{
              margin: 0,
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {rows.map((row) => {
              const item = row.settings;
              const detection = providerOfHost(item.host, item.port ?? null, [
                item,
              ]);
              const expiry = worstExpiry(
                row.credentials.map((c) => c.expires_at),
              );
              const version = shortVersion(detection.version);
              return (
                <li
                  key={row.key}
                  data-testid="server-row"
                  className="flex items-start"
                  style={{
                    gap: 10,
                    padding: 12,
                    borderRadius: "var(--r-2)",
                    border: "1px solid var(--border)",
                    background: "var(--bg-0)",
                    listStyle: "none",
                  }}
                >
                  <span
                    aria-hidden="true"
                    className="flex items-center justify-center"
                    style={{
                      width: 28,
                      height: 28,
                      flexShrink: 0,
                      borderRadius: "var(--r-2)",
                      background: "var(--bg-2)",
                      color: "var(--fg-1)",
                    }}
                  >
                    <Server size={14} />
                  </span>
                  <div
                    className="flex flex-col"
                    style={{ gap: 5, flex: 1, minWidth: 0 }}
                  >
                    <div
                      className="flex items-center"
                      style={{ gap: 6, flexWrap: "wrap" }}
                    >
                      <strong
                        className="mono truncate"
                        style={{ fontSize: 13, minWidth: 0 }}
                      >
                        {hostLabel(item.host, item.port)}
                      </strong>
                      <span
                        className="chip accent"
                        data-testid="server-provider"
                      >
                        {tRemote(`provider.${detection.id}`)}
                        {version !== "" ? ` · v${version}` : ""}
                      </span>
                      {item.ca_present && (
                        <span className="chip" data-testid="server-ca">
                          {t("servers.caPresent")}
                        </span>
                      )}
                      {item.pinned_fingerprint && (
                        <span
                          className="chip"
                          data-testid="server-pin"
                          title={item.pinned_fingerprint}
                        >
                          {t("servers.pinned")}
                        </span>
                      )}
                    </div>
                    <span className="dim" style={{ fontSize: 11.5 }}>
                      {t(`servers.detectedBy.${detection.detected_by}`)}
                      {" · "}
                      {t("servers.credentials", {
                        count: row.credentials.length,
                      })}
                    </span>
                    {expiry.state !== "none" && expiry.state !== "ok" && (
                      <span>
                        <ExpiryBadge
                          expiresAt={
                            row.credentials.find(
                              (c) =>
                                worstExpiry([c.expires_at]).state ===
                                expiry.state,
                            )?.expires_at
                          }
                        />
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn xs"
                    aria-label={t("servers.configureLabel", {
                      host: hostLabel(item.host, item.port),
                    })}
                    onClick={() => {
                      setEditing(item);
                    }}
                  >
                    {t("servers.configure")}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <div>
          <button
            type="button"
            className="btn sm"
            data-testid="server-add"
            onClick={() => {
              setEditing("new");
            }}
          >
            <Plus size={13} aria-hidden="true" />
            {t("servers.add")}
          </button>
        </div>
      </div>
      {editing !== null && (
        <HostSettingsDialog
          settings={editing === "new" ? null : editing}
          onClose={() => {
            setEditing(null);
          }}
        />
      )}
    </>
  );
};
