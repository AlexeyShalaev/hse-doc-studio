import { useRef, useState, type KeyboardEvent } from "react";
import { Bell, Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { formatPastTime } from "@shared/lib";
import { Button } from "@shared/ui/Button";
import { EmptyState } from "@shared/ui/EmptyState";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { Spinner } from "@shared/ui/Spinner";
import { useBootstrap } from "@entities/session";
import {
  useInboxSummary,
  useMarkNotificationsRead,
  useRecentNotifications,
  type Notification,
} from "@entities/invitation";
import { needsDecision, popoverAction } from "../lib/notificationTarget";
import { useNotificationText } from "../lib/useNotificationText";
import { NotificationIcon } from "./NotificationIcon";

/** Сколько последних уведомлений показывает окошко; остальные на странице «Входящие». */
export const BELL_POPOVER_LIMIT = 10;

/**
 * Колокольчик «Входящих» в шапке: число непрочитанных плюс ожидающие приглашения и передачи.
 * Нажатие открывает окошко с последними уведомлениями, страница «Входящие» остаётся для полного списка.
 */
export const InboxBell = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const boot = useBootstrap().data;
  const signedIn = boot?.mode === "server" && boot.user !== null;
  const summary = useInboxSummary(signedIn);
  const recent = useRecentNotifications(BELL_POPOVER_LIMIT, signedIn && open);
  const markRead = useMarkNotificationsRead();
  if (!signedIn) return null;
  const count = summary.data
    ? summary.data.unread + summary.data.invitations + summary.data.transfers
    : (boot.inbox?.unread ?? 0);
  const status = recent.data ? "ready" : recent.isError ? "error" : "loading";
  return (
    <InboxBellView
      count={count}
      open={open}
      onOpenChange={setOpen}
      status={status}
      notifications={recent.data?.items ?? []}
      onRetry={() => {
        void recent.refetch();
      }}
      onSelect={(n) => {
        const { route, markRead: shouldMark } = popoverAction(n);
        if (shouldMark) markRead.mutate([n.id]);
        setOpen(false);
        if (route) void navigate(route);
      }}
      onMarkAll={() => {
        markRead.mutate(null);
      }}
    />
  );
};

export type InboxBellViewProps = {
  /** Число на значке: непрочитанные, ожидающие приглашения и передачи. */
  count: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  status: "loading" | "error" | "ready";
  notifications: Notification[];
  onRetry: () => void;
  onSelect: (n: Notification) => void;
  onMarkAll: () => void;
};

const BADGE_MAX = 99;

/** Колокольчик и окошко под ним: чистый вид без запросов. */
export const InboxBellView = ({
  count,
  open,
  onOpenChange,
  status,
  notifications,
  onRetry,
  onSelect,
  onMarkAll,
}: InboxBellViewProps) => {
  const { t } = useTranslation("inbox");
  const text = useNotificationText();
  const contentRef = useRef<HTMLDivElement>(null);
  const label = count > 0 ? t("bell", { count }) : t("bellNone");
  const unreadInList = notifications.filter((n) => n.read_at === null).length;

  const items = () =>
    Array.from(
      contentRef.current?.querySelectorAll<HTMLElement>("[data-notif-item]") ??
        [],
    );
  const onListKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    const all = items();
    const at = all.indexOf(document.activeElement as HTMLElement);
    const move = (to: number) => {
      e.preventDefault();
      all[(to + all.length) % all.length]?.focus();
    };
    if (e.key === "ArrowDown") move(at + 1);
    else if (e.key === "ArrowUp") move(at < 0 ? -1 : at - 1);
    else if (e.key === "Home") move(0);
    else if (e.key === "End") move(-1);
  };

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="icon-btn tt"
          data-tt={label}
          aria-label={label}
          data-testid="inbox-bell"
          data-count={count}
          style={{ width: 32, height: 32, position: "relative" }}
        >
          <Bell size={16} aria-hidden="true" />
          {count > 0 && (
            <span
              aria-hidden="true"
              data-testid="inbox-bell-badge"
              style={{
                position: "absolute",
                top: 3,
                right: 2,
                minWidth: 15,
                height: 15,
                padding: "0 4px",
                borderRadius: 8,
                background: "var(--c-err)",
                color: "white",
                fontSize: 9.5,
                fontWeight: 600,
                lineHeight: "15px",
                textAlign: "center",
              }}
            >
              {count > BADGE_MAX ? "99+" : count}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        ref={contentRef}
        width={380}
        aria-label={t("popover.title")}
        data-testid="inbox-popover"
        style={{
          display: "flex",
          flexDirection: "column",
          overflowY: "hidden",
        }}
        onOpenAutoFocus={(e) => {
          const first = items()[0];
          if (first) {
            e.preventDefault();
            first.focus();
          }
        }}
      >
        <div
          className="flex items-center justify-between shrink-0"
          style={{
            gap: 8,
            padding: "8px 8px 8px 12px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-0)" }}>
            {t("popover.title")}
          </span>
          {unreadInList > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="xs"
              data-testid="inbox-popover-mark-all"
              onClick={onMarkAll}
            >
              {t("markAll")}
            </Button>
          )}
        </div>

        <div style={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto" }}>
          {status === "loading" && (
            <div
              className="flex items-center justify-center"
              style={{
                gap: 8,
                padding: 24,
                color: "var(--fg-2)",
                fontSize: 12.5,
              }}
              data-testid="inbox-popover-loading"
            >
              <Spinner size="sm" />
              {t("popover.loading")}
            </div>
          )}
          {status === "error" && (
            <div data-testid="inbox-popover-error" role="alert">
              <EmptyState
                compact
                title={t("popover.error")}
                action={
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    data-testid="inbox-popover-retry"
                    onClick={onRetry}
                  >
                    {t("popover.retry")}
                  </Button>
                }
              />
            </div>
          )}
          {status === "ready" && notifications.length === 0 && (
            <div data-testid="inbox-popover-empty">
              <EmptyState
                compact
                icon={<Inbox size={15} />}
                title={t("popover.empty")}
              />
            </div>
          )}
          {status === "ready" && notifications.length > 0 && (
            <ul
              aria-label={t("popover.list")}
              data-testid="inbox-popover-list"
              style={{ listStyle: "none", margin: 0, padding: 0 }}
              onKeyDown={onListKeyDown}
            >
              {notifications.map((n) => {
                const unread = n.read_at === null;
                return (
                  <li key={n.id}>
                    <button
                      type="button"
                      className="notif-item"
                      data-notif-item=""
                      data-testid={`inbox-popover-item-${n.id}`}
                      data-unread={unread}
                      onClick={() => {
                        onSelect(n);
                      }}
                    >
                      <span
                        className="shrink-0"
                        style={{
                          marginTop: 1,
                          color: unread ? "var(--accent)" : "var(--fg-3)",
                        }}
                      >
                        <NotificationIcon kind={n.kind} />
                      </span>
                      <span
                        className="flex flex-col min-w-0"
                        style={{ flex: 1, gap: 2 }}
                      >
                        <span
                          style={{
                            fontWeight: unread ? 600 : 400,
                            overflowWrap: "anywhere",
                            display: "-webkit-box",
                            WebkitLineClamp: 3,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }}
                        >
                          {unread && (
                            <span className="sr-only">
                              {t("popover.unread")}:{" "}
                            </span>
                          )}
                          {text(n)}
                        </span>
                        <span style={{ fontSize: 11, color: "var(--fg-2)" }}>
                          {formatPastTime(n.created_at)}
                          {needsDecision(n) && (
                            <>
                              {" · "}
                              <span style={{ color: "var(--accent)" }}>
                                {t("popover.decision")}
                              </span>
                            </>
                          )}
                        </span>
                      </span>
                      {unread && (
                        <span
                          aria-hidden="true"
                          data-testid="inbox-popover-unread-dot"
                          className="shrink-0"
                          style={{
                            width: 7,
                            height: 7,
                            marginTop: 5,
                            borderRadius: "50%",
                            background: "var(--accent)",
                          }}
                        />
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div
          className="flex shrink-0"
          style={{ padding: 6, borderTop: "1px solid var(--border)" }}
        >
          <Button
            asChild
            variant="ghost"
            size="sm"
            style={{ width: "100%", textDecoration: "none" }}
          >
            <Link
              to="/inbox"
              data-testid="inbox-popover-all"
              onClick={() => {
                onOpenChange(false);
              }}
            >
              {t("popover.showAll")}
            </Link>
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
};
