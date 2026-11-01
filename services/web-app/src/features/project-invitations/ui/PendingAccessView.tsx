import { useState } from "react";
import { Mail, UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ActionMenu, Badge, Button } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useProjectRoleLabel } from "@entities/project";
import type {
  AccessRequestView,
  ProjectInvitation,
} from "@entities/invitation";
import { daysLeft, formatDate } from "../lib/time";

export type PendingAccessViewProps = {
  invitations: ProjectInvitation[];
  requests: AccessRequestView[];
  /** Передача владения ждёт подтверждения: видят все участники. */
  transferPending?: boolean;
  busyId?: string | null;
  now?: number;
  lang?: string;
  onResend: (inv: ProjectInvitation) => void;
  onRevoke: (inv: ProjectInvitation) => void;
  onApprove: (req: AccessRequestView) => void;
  onDeny: (req: AccessRequestView) => void;
};

const CARD = {
  padding: 16,
  borderRadius: "var(--r-3)",
  border: "1px solid var(--border)",
  background: "var(--bg-1)",
  display: "flex",
  flexDirection: "column",
  gap: 12,
} as const;

const ROW = {
  gap: 12,
  padding: "10px 0",
  borderBottom: "1px dashed var(--border)",
} as const;

/** «Ожидают» в панели «Доступ» (10.7): приглашения и запросы доступа; пустые блоки скрыты. */
export const PendingAccessView = ({
  invitations,
  requests,
  transferPending = false,
  busyId = null,
  now: nowProp,
  lang = "ru",
  onResend,
  onRevoke,
  onApprove,
  onDeny,
}: PendingAccessViewProps) => {
  const [mounted] = useState(() => Date.now());
  const now = nowProp ?? mounted;
  const { t } = useTranslation("invitations");
  const roleLabel = useProjectRoleLabel();
  if (invitations.length === 0 && requests.length === 0 && !transferPending) {
    return null;
  }
  return (
    <section style={CARD} data-testid="project-access-pending">
      <div className="flex flex-col" style={{ gap: 3 }}>
        <h5 style={{ margin: 0, fontSize: 13.5, fontWeight: 600 }}>
          {t("pending.title")}
        </h5>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>
          {t("pending.lead")}
        </p>
      </div>
      {transferPending && (
        <div data-testid="project-transfer-notice">
          <Notice tone="info" text={t("transfer.pendingNotice")} />
        </div>
      )}
      {invitations.length > 0 && (
        <div data-testid="pending-invitations">
          <strong style={{ fontSize: 12.5 }}>{t("pending.invitations")}</strong>
          <ul
            style={{ listStyle: "none", margin: 0, padding: 0 }}
            className="flex flex-col"
          >
            {invitations.map((inv) => {
              const left = daysLeft(inv.expires_at, now);
              const expired = inv.status === "expired" || left < 0;
              const who =
                inv.invitee.kind === "user"
                  ? (inv.invitee.name ?? "")
                  : (inv.invitee.email_hint ?? "");
              const Icon = inv.invitee.kind === "user" ? UserRound : Mail;
              return (
                <li
                  key={inv.id}
                  className="flex items-center"
                  style={ROW}
                  data-testid={`invitation-row-${inv.id}`}
                  data-state={expired ? "expired" : "pending"}
                >
                  <Icon
                    size={16}
                    aria-hidden="true"
                    style={{ color: "var(--fg-2)", flexShrink: 0 }}
                  />
                  <div
                    className="flex flex-col"
                    style={{ gap: 2, flex: 1, minWidth: 0 }}
                  >
                    <span
                      className="flex items-center"
                      style={{ gap: 8, fontSize: 13, flexWrap: "wrap" }}
                    >
                      <span style={{ overflowWrap: "anywhere" }}>{who}</span>
                      <Badge variant="default">{roleLabel(inv.role)}</Badge>
                      {inv.persona && (
                        <Badge variant="subtle">
                          {t(`persona.${inv.persona}`, {
                            defaultValue: inv.persona,
                          })}
                        </Badge>
                      )}
                    </span>
                    <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                      {t("pending.sent", {
                        count: inv.sent_count,
                        date: formatDate(inv.last_sent_at, lang),
                      })}
                      {" · "}
                      {expired
                        ? t("pending.expired")
                        : t("pending.expiresIn", { count: left })}
                    </span>
                  </div>
                  <ActionMenu
                    label={t("pending.actions", { name: who })}
                    testId={`invitation-actions-${inv.id}`}
                    items={[
                      {
                        id: "resend",
                        label: t("pending.resend"),
                        disabled: busyId === inv.id,
                        testId: `invitation-resend-${inv.id}`,
                        onSelect: () => {
                          onResend(inv);
                        },
                      },
                      {
                        id: "revoke",
                        label: t("pending.revoke"),
                        danger: true,
                        disabled: busyId === inv.id,
                        testId: `invitation-revoke-${inv.id}`,
                        onSelect: () => {
                          onRevoke(inv);
                        },
                      },
                    ]}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {requests.length > 0 && (
        <div data-testid="pending-access-requests">
          <strong style={{ fontSize: 12.5 }}>{t("pending.requests")}</strong>
          <ul
            style={{ listStyle: "none", margin: 0, padding: 0 }}
            className="flex flex-col"
          >
            {requests.map((req) => (
              <li
                key={req.id}
                className="flex items-center"
                style={ROW}
                data-testid={`access-request-row-${req.id}`}
              >
                <UserRound
                  size={16}
                  aria-hidden="true"
                  style={{ color: "var(--fg-2)", flexShrink: 0 }}
                />
                <div
                  className="flex flex-col"
                  style={{ gap: 2, flex: 1, minWidth: 0 }}
                >
                  <span style={{ fontSize: 13 }}>
                    {req.requester.name}{" "}
                    <span className="dim" style={{ fontSize: 11.5 }}>
                      {req.requester.email}
                    </span>
                  </span>
                  {req.message && (
                    <span style={{ fontSize: 12, fontStyle: "italic" }}>
                      «{req.message}»
                    </span>
                  )}
                  <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                    {formatDate(req.created_at, lang)}
                  </span>
                </div>
                <Button
                  type="button"
                  size="xs"
                  disabled={busyId === req.id}
                  data-testid={`access-request-approve-${req.id}`}
                  onClick={() => {
                    onApprove(req);
                  }}
                >
                  {t("requests.approve")}
                </Button>
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  disabled={busyId === req.id}
                  data-testid={`access-request-deny-${req.id}`}
                  onClick={() => {
                    onDeny(req);
                  }}
                >
                  {t("requests.deny")}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};
