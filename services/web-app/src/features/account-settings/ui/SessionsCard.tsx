import { useState } from "react";
import { Laptop, LogOut, Smartphone } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import { Badge, Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AccountSession } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { describeAgent } from "../lib/device";
import { ACTIONS } from "../lib/styles";
import { AccountCard } from "./parts";

export type SessionsCardProps = {
  status: "loading" | "error" | "ready";
  sessions?: AccountSession[];
  /** Идентификатор сессии, которую завершают сейчас. */
  revokingId?: string | null;
  revokingOthers?: boolean;
  failure?: Failure | null;
  onRetry?: () => void;
  onRevoke: (id: string) => void;
  onRevokeOthers: () => void;
};

const isMobile = (agent: string): boolean =>
  /android|iphone|ipad|ios/i.test(agent);

/** Активные входы человека. Текущую сессию завершить нельзя: для неё есть «Выйти». */
export const SessionsCard = ({
  status,
  sessions = [],
  revokingId = null,
  revokingOthers = false,
  failure = null,
  onRetry,
  onRevoke,
  onRevokeOthers,
}: SessionsCardProps) => {
  const { t } = useTranslation("account");
  const [confirmAll, setConfirmAll] = useState(false);
  const others = sessions.filter((s) => !s.current);
  const ordered = [...sessions].sort(
    (a, b) => Number(b.current) - Number(a.current),
  );

  return (
    <AccountCard
      id="account-sessions"
      title={t("sessions.title")}
      sub={t("sessions.sub")}
      testId="account-sessions"
    >
      {status === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 12 }}
          data-testid="sessions-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("sessions.loading")}</span>
        </div>
      )}

      {status === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("sessions.loadFailed")}
          action={
            onRetry && (
              <button type="button" className="btn xs" onClick={onRetry}>
                {t("sessions.retry")}
              </button>
            )
          }
        />
      )}

      {status === "ready" && (
        <>
          <ul
            style={{ listStyle: "none", margin: 0, padding: 0 }}
            className="flex flex-col"
            data-testid="sessions-list"
          >
            {ordered.map((session) => {
              const Icon = isMobile(session.user_agent) ? Smartphone : Laptop;
              const busy = revokingId === session.id;
              return (
                <li
                  key={session.id}
                  data-testid={`session-${session.id}`}
                  data-current={session.current ? "true" : undefined}
                  className="flex items-center"
                  style={{
                    gap: 12,
                    padding: "10px 0",
                    borderBottom: "1px dashed var(--border)",
                  }}
                >
                  <Icon
                    size={18}
                    aria-hidden="true"
                    style={{ color: "var(--fg-2)", flexShrink: 0 }}
                  />
                  <div
                    className="flex flex-col"
                    style={{ gap: 2, flex: 1, minWidth: 0 }}
                  >
                    <span
                      className="flex items-center"
                      style={{
                        gap: 8,
                        fontSize: 13,
                        fontWeight: 500,
                        flexWrap: "wrap",
                      }}
                    >
                      <span
                        style={{ overflowWrap: "anywhere" }}
                        title={session.user_agent || undefined}
                      >
                        {describeAgent(session.user_agent) ||
                          session.user_agent ||
                          t("sessions.unknownDevice")}
                      </span>
                      {session.current && (
                        <Badge variant="success">{t("sessions.current")}</Badge>
                      )}
                    </span>
                    <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                      {t("sessions.lastSeen", {
                        when: formatPastTime(session.last_seen_at),
                      })}
                      {" · "}
                      {session.ip ?? t("sessions.noIp")}
                    </span>
                  </div>
                  {session.current ? (
                    <span
                      style={{
                        fontSize: 11.5,
                        color: "var(--fg-2)",
                        maxWidth: 150,
                        textAlign: "right",
                      }}
                    >
                      {t("sessions.currentHint")}
                    </span>
                  ) : (
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      aria-disabled={busy || revokingOthers}
                      aria-label={t("sessions.endAria", {
                        device:
                          session.user_agent || t("sessions.unknownDevice"),
                      })}
                      onClick={() => {
                        if (!busy && !revokingOthers) onRevoke(session.id);
                      }}
                      style={{ gap: 6 }}
                    >
                      {busy ? (
                        <Spinner size="sm" />
                      ) : (
                        <LogOut size={12} aria-hidden="true" />
                      )}
                      {t("sessions.end")}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>

          {failure && (
            <Notice
              tone="err"
              role="alert"
              text={t(failureKey(failure.code))}
            />
          )}

          {others.length === 0 ? (
            <p
              style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}
              data-testid="sessions-alone"
            >
              {t("sessions.alone")}
            </p>
          ) : confirmAll ? (
            <div
              style={ACTIONS}
              role="group"
              aria-label={t("sessions.confirmAll", { count: others.length })}
            >
              <span style={{ fontSize: 12.5 }}>
                {t("sessions.confirmAll", { count: others.length })}
              </span>
              <Button
                type="button"
                variant="danger"
                size="sm"
                aria-disabled={revokingOthers}
                data-testid="sessions-end-others-confirm"
                onClick={() => {
                  if (revokingOthers) return;
                  onRevokeOthers();
                  setConfirmAll(false);
                }}
              >
                {t("sessions.confirmYes")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setConfirmAll(false);
                }}
              >
                {t("sessions.confirmNo")}
              </Button>
            </div>
          ) : (
            <div style={ACTIONS}>
              <Button
                type="button"
                variant="outline"
                aria-disabled={revokingOthers || revokingId !== null}
                data-testid="sessions-end-others"
                style={{ gap: 8 }}
                onClick={() => {
                  setConfirmAll(true);
                }}
              >
                {revokingOthers ? (
                  <Spinner size="sm" />
                ) : (
                  <LogOut size={14} aria-hidden="true" />
                )}
                {t("sessions.endOthers", { count: others.length })}
              </Button>
            </div>
          )}
        </>
      )}
    </AccountCard>
  );
};
