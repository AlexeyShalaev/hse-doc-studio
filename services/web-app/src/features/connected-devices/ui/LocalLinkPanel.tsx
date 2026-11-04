import { Cloud, KeyRound, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  AI_DOT,
  AiAdvice,
  DeviceCard,
  cloudSeesOnline,
  type LinkServer,
  type StudioLink,
} from "@entities/connected-device";
import { formatPastTime } from "@shared/lib";
import { StatusDot, type StatusDotStatus } from "@shared/ui/StatusDot";
import { pickServer } from "../model/summary";

const SERVER_DOT: Record<LinkServer["state"], StatusDotStatus> = {
  ok: "online",
  expired: "danger",
  revoked: "danger",
  unreachable: "stale",
};

const Section = ({
  title,
  children,
  testId,
}: {
  title: string;
  children: React.ReactNode;
  testId?: string;
}) => (
  <div
    className="flex flex-col"
    style={{ gap: 5, paddingTop: 8, borderTop: "1px solid var(--border)" }}
    data-testid={testId}
  >
    <span
      className="dim"
      style={{
        fontSize: 10.5,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
      }}
    >
      {title}
    </span>
    {children}
  </div>
);

const ServerRows = ({ server, now }: { server: LinkServer; now: number }) => {
  const { t } = useTranslation("devices");
  const sees = cloudSeesOnline(server)
    ? t("local.cloudSeesOnline")
    : server.cloud?.device
      ? t("local.cloudSeesOffline")
      : t("local.cloudSeesWaiting");
  return (
    <div className="flex flex-col" style={{ gap: 4 }} data-testid="link-server">
      <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
        <Cloud size={13} style={{ color: "var(--fg-2)" }} />
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>
          {t("local.server", { host: server.host })}
        </span>
        <StatusDot
          status={SERVER_DOT[server.state]}
          label={t(`local.state.${server.state}`)}
        />
      </div>
      {server.account_name !== null && (
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("local.account", { name: server.account_name })}
        </span>
      )}
      {(server.state === "expired" || server.state === "revoked") && (
        <span
          className="flex items-center"
          style={{ gap: 6, fontSize: 11.5, color: "var(--c-warn)" }}
          data-testid="link-relogin"
        >
          <KeyRound size={12} />
          {t("local.relogin")}
        </span>
      )}
      {server.state === "ok" && (
        <>
          <span style={{ fontSize: 12 }} data-testid="link-cloud-sees">
            {t("local.cloudSees", { state: sees })}
          </span>
          <span
            className="dim"
            style={{
              fontSize: 11.5,
              color: server.last?.ok === false ? "var(--c-warn)" : undefined,
            }}
            data-testid="link-last-sent"
          >
            {server.last === null
              ? t("local.noSignal")
              : server.last.ok
                ? t("local.lastSent", {
                    when: formatPastTime(server.last.at, now),
                  })
                : t("local.lastFailed", { code: server.last.code ?? "?" })}
          </span>
          {server.cloud_error !== null && (
            <span style={{ fontSize: 11.5, color: "var(--c-warn)" }}>
              {t("local.cloudError", { code: server.cloud_error })}
            </span>
          )}
        </>
      )}
    </div>
  );
};

export type LocalLinkPanelProps = {
  link: StudioLink;
  now: number;
  /** Внутри раздела настроек: без своего заголовка, рамки прокрутки и отступов. */
  embedded?: boolean;
};

/**
 * Панель локальной Студии: то же, что облако знает о ней, глазами самой Студии. Карточка устройства та же, что в
 * облаке (там это «ваша Студия»), а сверху добавлено состояние входа на сервер и кто ещё работает в проекте.
 */
export const LocalLinkPanel = ({
  link,
  now,
  embedded = false,
}: LocalLinkPanelProps) => {
  const { t } = useTranslation("devices");
  const server = pickServer(link);
  if (server === null) return null;
  const device = server.cloud?.device ?? null;
  const others = server.cloud?.others ?? [];
  const announced = link.endpoints.filter((e) => e.announced);
  return (
    <div
      className="flex flex-col"
      style={
        embedded
          ? { gap: 10 }
          : { gap: 10, padding: 12, maxHeight: "70vh", overflowY: "auto" }
      }
      data-testid="local-link-panel"
    >
      {!embedded && (
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>
          {t("local.title")}
        </span>
      )}
      <ServerRows server={server} now={now} />
      {device !== null && <DeviceCard device={device} now={now} />}
      <Section title={t("local.allowed")} testId="link-allowed">
        {!link.runner.enabled && announced.length === 0 ? (
          <span className="dim" style={{ fontSize: 11.5 }}>
            {t("local.allowedNone")}
          </span>
        ) : (
          <>
            <span style={{ fontSize: 12 }}>
              {t("local.allowedRunner", {
                state: t(`card.runnerState.${runnerStateKey(link)}`),
              })}
            </span>
            {announced.map((endpoint) => {
              const cloud = device?.ai.endpoints.find(
                (e) => e.name === endpoint.name,
              );
              return (
                <div
                  key={endpoint.name}
                  className="flex flex-col"
                  style={{ gap: 2 }}
                  data-testid={`link-endpoint-${endpoint.name}`}
                >
                  <StatusDot
                    status={AI_DOT[cloud?.state ?? "unknown"]}
                    label={`${endpoint.name}: ${t(`ai.state.${cloud?.state ?? "unknown"}`)}`}
                  />
                  <AiAdvice state={cloud?.state ?? "unknown"} />
                </div>
              );
            })}
          </>
        )}
      </Section>
      <Section title={t("local.othersTitle")} testId="link-others">
        {others.length === 0 ? (
          <span className="dim" style={{ fontSize: 11.5 }}>
            {t("local.othersEmpty")}
          </span>
        ) : (
          others.map((person) => (
            <div
              key={person.user_id}
              className="flex items-center"
              style={{ gap: 8, fontSize: 12.5 }}
            >
              <Users size={13} style={{ color: "var(--fg-2)" }} />
              {t("panel.workingLocally", { name: person.name })}
            </div>
          ))
        )}
      </Section>
    </div>
  );
};

/** Состояние раннера для строки «что открыто облаку»: из собственных данных Студии. */
const runnerStateKey = (link: StudioLink): string => {
  const state = link.runner.state;
  if (state === "online") return "online";
  if (state === "paused") return "paused";
  if (state === "revoked") return "revoked";
  if (state === "disabled") return "disabled";
  return "offline";
};
