import { useState } from "react";
import { Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, EmptyState } from "@shared/ui";
import { useProjectRoleLabel } from "@entities/project";
import type {
  MyAccessRequest,
  MyInvitation,
  MyTransfer,
  Notification,
} from "@entities/invitation";

export type InboxTab = "all" | "invitations" | "requests" | "transfers";

export type InboxViewProps = {
  tab: InboxTab;
  onTab: (tab: InboxTab) => void;
  invitations: MyInvitation[];
  transfers: MyTransfer[];
  notifications: Notification[];
  myRequests: MyAccessRequest[];
  busyId?: string | null;
  lang?: string;
  onInvitation: (inv: MyInvitation, accept: boolean) => void;
  onTransfer: (tr: MyTransfer, accept: boolean) => void;
  onRequestDecision: (n: Notification, approve: boolean) => void;
  onNotification: (n: Notification) => void;
  onMarkAll: () => void;
  onCancelRequest: (r: MyAccessRequest) => void;
};

const CARD = {
  padding: 14,
  borderRadius: "var(--r-3)",
  border: "1px solid var(--border)",
  background: "var(--bg-1)",
  display: "flex",
  flexDirection: "column",
  gap: 8,
} as const;

const date = (iso: string, lang: string) =>
  new Date(iso).toLocaleDateString(lang === "en" ? "en-GB" : "ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

/** Страница «Входящие» (10.9): приглашения, передачи, запросы в моих проектах и уведомления. */
export const InboxView = ({
  tab,
  onTab,
  invitations,
  transfers,
  notifications,
  myRequests,
  busyId = null,
  lang = "ru",
  onInvitation,
  onTransfer,
  onRequestDecision,
  onNotification,
  onMarkAll,
  onCancelRequest,
}: InboxViewProps) => {
  const { t } = useTranslation("inbox");
  const roleLabel = useProjectRoleLabel();
  const [now] = useState(() => Date.now());
  const requestCards = notifications.filter(
    (n) => n.kind === "access_request" && n.read_at === null,
  );
  const feed = notifications.filter(
    (n) => !(n.kind === "access_request" && n.read_at === null),
  );
  const show = (what: InboxTab) => tab === "all" || tab === what;
  const empty =
    invitations.length === 0 &&
    transfers.length === 0 &&
    notifications.length === 0 &&
    myRequests.length === 0;
  const unread = notifications.filter((n) => n.read_at === null).length;

  const tabs: InboxTab[] = ["all", "invitations", "requests", "transfers"];

  return (
    <main
      className="flex flex-col"
      style={{ padding: "24px 32px", gap: 16, maxWidth: 860, width: "100%" }}
      data-testid="inbox-page"
    >
      <div className="flex items-center justify-between" style={{ gap: 12 }}>
        <h1 style={{ margin: 0, fontSize: 20 }}>{t("title")}</h1>
        {unread > 0 && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            data-testid="inbox-mark-all-read"
            onClick={onMarkAll}
          >
            {t("markAll")}
          </Button>
        )}
      </div>
      <div role="tablist" className="flex" style={{ gap: 4 }}>
        {tabs.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={`btn sm ${tab === id ? "primary" : "ghost"}`}
            data-testid={`inbox-tab-${id}`}
            onClick={() => {
              onTab(id);
            }}
          >
            {t(`tabs.${id}`)}
          </button>
        ))}
      </div>

      {empty && (
        <div data-testid="inbox-empty">
          <EmptyState icon={<Inbox size={22} />} title={t("empty")} />
        </div>
      )}

      {show("invitations") &&
        invitations.map((inv) => {
          const expired =
            inv.status === "expired" ||
            new Date(inv.expires_at).getTime() <= now;
          return (
            <section
              key={inv.id}
              style={CARD}
              data-testid={`inbox-invitation-${inv.id}`}
              data-state={expired ? "expired" : "pending"}
            >
              <strong style={{ fontSize: 13.5 }}>
                {t("invitation.title", {
                  actor: inv.invited_by?.name ?? inv.project.owner_name,
                  project: inv.project.name,
                })}
              </strong>
              <span className="flex items-center" style={{ gap: 8 }}>
                <Badge>{roleLabel(inv.role)}</Badge>
                {inv.persona && (
                  <Badge variant="subtle">
                    {t(`invitations:persona.${inv.persona}`, {
                      defaultValue: inv.persona,
                    })}
                  </Badge>
                )}
                <span className="dim" style={{ fontSize: 11.5 }}>
                  {expired
                    ? t("invitation.expired")
                    : t("invitation.until", {
                        date: date(inv.expires_at, lang),
                      })}
                </span>
              </span>
              {inv.message && (
                <p style={{ margin: 0, fontSize: 12.5, fontStyle: "italic" }}>
                  «{inv.message}»
                </p>
              )}
              {!expired && (
                <div className="flex" style={{ gap: 8 }}>
                  <Button
                    type="button"
                    size="sm"
                    disabled={busyId === inv.id}
                    data-testid={`inbox-invitation-accept-${inv.id}`}
                    onClick={() => {
                      onInvitation(inv, true);
                    }}
                  >
                    {t("accept")}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={busyId === inv.id}
                    data-testid={`inbox-invitation-decline-${inv.id}`}
                    onClick={() => {
                      onInvitation(inv, false);
                    }}
                  >
                    {t("decline")}
                  </Button>
                </div>
              )}
            </section>
          );
        })}

      {show("transfers") &&
        transfers.map((tr) => (
          <section
            key={tr.id}
            style={CARD}
            data-testid={`inbox-transfer-${tr.id}`}
            data-state={tr.status}
          >
            <strong style={{ fontSize: 13.5 }}>
              {t("transfer.title", {
                actor: tr.from.name,
                project: tr.project.name,
              })}
            </strong>
            <span className="dim" style={{ fontSize: 12 }}>
              {tr.previous_owner_role
                ? t("transfer.becomesEditor", { actor: tr.from.name })
                : t("transfer.fromOrg")}
              {" · "}
              {t("invitation.until", { date: date(tr.expires_at, lang) })}
            </span>
            {tr.status === "pending" && (
              <div className="flex" style={{ gap: 8 }}>
                <Button
                  type="button"
                  size="sm"
                  disabled={busyId === tr.id}
                  data-testid={`inbox-transfer-accept-${tr.id}`}
                  onClick={() => {
                    onTransfer(tr, true);
                  }}
                >
                  {t("accept")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={busyId === tr.id}
                  data-testid={`inbox-transfer-decline-${tr.id}`}
                  onClick={() => {
                    onTransfer(tr, false);
                  }}
                >
                  {t("decline")}
                </Button>
              </div>
            )}
          </section>
        ))}

      {show("requests") &&
        requestCards.map((n) => (
          <section
            key={n.id}
            style={CARD}
            data-testid={`inbox-access-request-${n.payload.ref_id ?? n.id}`}
          >
            <strong style={{ fontSize: 13.5 }}>
              {t("request.title", {
                actor: n.payload.actor_name ?? "",
                project: n.payload.project_name ?? "",
              })}
            </strong>
            <span className="dim" style={{ fontSize: 11.5 }}>
              {date(n.created_at, lang)}
            </span>
            <div className="flex" style={{ gap: 8 }}>
              <Button
                type="button"
                size="sm"
                disabled={busyId === n.id}
                data-testid={`inbox-access-request-approve-${n.payload.ref_id ?? n.id}`}
                onClick={() => {
                  onRequestDecision(n, true);
                }}
              >
                {t("approve")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busyId === n.id}
                data-testid={`inbox-access-request-deny-${n.payload.ref_id ?? n.id}`}
                onClick={() => {
                  onRequestDecision(n, false);
                }}
              >
                {t("deny")}
              </Button>
            </div>
          </section>
        ))}

      {show("requests") && myRequests.length > 0 && (
        <section style={CARD} data-testid="inbox-my-requests">
          <strong style={{ fontSize: 13 }}>{t("myRequests.title")}</strong>
          {myRequests.map((r) => (
            <div
              key={r.id}
              className="flex items-center justify-between"
              style={{ gap: 8, fontSize: 12.5 }}
              data-testid={`inbox-my-request-${r.id}`}
            >
              <span>
                {r.project.name ?? t("myRequests.hidden")}
                {" · "}
                <span className="dim">
                  {t(`myRequests.status.${r.status}`)}
                  {r.granted_role ? `: ${roleLabel(r.granted_role)}` : ""}
                </span>
              </span>
              {r.status === "pending" && (
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  disabled={busyId === r.id}
                  data-testid={`inbox-my-request-cancel-${r.id}`}
                  onClick={() => {
                    onCancelRequest(r);
                  }}
                >
                  {t("myRequests.cancel")}
                </Button>
              )}
            </div>
          ))}
        </section>
      )}

      {tab === "all" && feed.length > 0 && (
        <section style={CARD} data-testid="inbox-notifications">
          <strong style={{ fontSize: 13 }}>{t("feed")}</strong>
          {feed.map((n) => (
            <button
              key={n.id}
              type="button"
              className="flex items-center"
              data-testid={`inbox-notification-${n.id}`}
              data-read={n.read_at !== null}
              style={{
                gap: 8,
                textAlign: "left",
                padding: "6px 0",
                fontSize: 12.5,
                fontWeight: n.read_at === null ? 600 : 400,
                color: n.read_at === null ? "var(--fg-0)" : "var(--fg-1)",
                background: "transparent",
                border: 0,
                borderBottom: "1px dashed var(--border)",
              }}
              onClick={() => {
                onNotification(n);
              }}
            >
              {n.read_at === null && (
                <span
                  aria-hidden="true"
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 3,
                    background: "var(--accent)",
                  }}
                />
              )}
              <span style={{ flex: 1 }}>
                {t(`kind.${n.kind}`, {
                  actor: n.payload.actor_name ?? "",
                  project: n.payload.project_name ?? "",
                  role: n.payload.role
                    ? roleLabel(n.payload.role as "reader")
                    : "",
                  ...(n.payload.outcome ? { context: n.payload.outcome } : {}),
                })}
              </span>
              <span className="dim" style={{ fontSize: 11 }}>
                {date(n.created_at, lang)}
              </span>
            </button>
          ))}
        </section>
      )}
    </main>
  );
};
